import json
import unittest

from pydantic import ValidationError

from app.agents.contracts import (
    BoardSynthesis,
    ExecutiveAssessment,
    TargetedChallenge,
    PositionRevision,
    assessment_for_board,
    board_synthesis_markdown,
    build_position_extraction,
    format_challenge_docket,
    format_targeted_cross_examination,
    parse_assessment_checkpoint,
    parse_structured_output,
    parse_revision_for_assessment,
    parse_targeted_cross_examination,
    validate_assessment_evidence_references,
)
from app.agents.prompts import (
    EXECUTIVE_PROFILE_VERSION,
    EXECUTIVE_PROFILES,
    executive_system_prompt,
)


def valid_assessment():
    return {
        "schema_version": 1,
        "executive_position": "conditional",
        "recommendation": "Run a bounded customer discovery pilot.",
        "confidence": "medium",
        "supporting_facts": [
            {"claim": "The founder supplied an epilepsy focus.", "classification": "founder-provided"}
        ],
        "assumptions": [
            {"claim": "Clinics will participate in interviews.", "classification": "assumption"}
        ],
        "hypotheses": [
            {"claim": "A narrow workflow may have an unmet need.", "classification": "hypothesis"}
        ],
        "unknowns": [
            {"claim": "Willingness to pay is not established.", "classification": "unknown"}
        ],
        "risks": [{"claim": "Recruitment may take longer than expected.", "classification": "estimate"}],
        "alternatives": [{"claim": "Interview caregivers first.", "classification": "hypothesis"}],
        "dependencies": [{"claim": "Qualified clinical review is needed.", "classification": "unknown"}],
        "success_criteria": [{"claim": "Complete 10 interviews.", "classification": "estimate"}],
        "decision_gates": [{"claim": "Proceed only after evidence review.", "classification": "hypothesis"}],
    }


def valid_revision(position_change, previous, revised):
    return {
        "schema_version": 1,
        "position_change": position_change,
        "previous_position": previous,
        "revised_position": revised,
        "reason_for_change": "The challenge surfaced a dependency that changes the sequence.",
        "arguments_that_changed_my_view": [
            {"claim": "The data provenance is not documented.", "classification": "unknown"}
        ],
        "remaining_disagreements": [
            {"claim": "The pilot scope is still too broad.", "classification": "assumption"}
        ],
    }


def valid_assessment_json(role, position="conditional"):
    assessment = valid_assessment()
    assessment["executive_position"] = position
    assessment["recommendation"] = f"{role} recommendation."
    return json.dumps(assessment)


def valid_cross_examination(challenger_role):
    roles = ("CEO", "CFO", "CTO", "CSO")
    return {
        "schema_version": 1,
        "challenges": [
            {
                "target_role": target_role,
                "target_claim_id": f"{target_role}.recommendation",
                "challenge_question": f"What evidence supports {target_role}'s recommendation?",
                "why_it_matters": "The decision depends on this recommendation.",
            }
            for target_role in roles
            if target_role != challenger_role
        ],
    }


class StructuredOutputTests(unittest.TestCase):
    def test_valid_structured_assessment_requires_tagged_claims(self):
        assessment = ExecutiveAssessment.model_validate(valid_assessment())
        self.assertEqual(assessment.executive_position, "conditional")
        self.assertEqual(assessment.supporting_facts[0].classification, "founder-provided")
        self.assertEqual(assessment.assumptions[0].classification, "assumption")
        self.assertEqual(assessment.decision_gates[0].classification, "hypothesis")

    def test_assessment_parser_rejects_malformed_and_incomplete_output(self):
        for content in (
            "not JSON",
            '{"schema_version":1,"executive_position":"proceed"}',
            '{"schema_version":1,"executive_position":"proceed","recommendation":"Go","confidence":"certain"}',
        ):
            with self.subTest(content=content), self.assertRaises(ValueError):
                parse_structured_output(content, ExecutiveAssessment)

    def test_assessment_for_board_preserves_claim_classification_and_labels_legacy(self):
        assessment = ExecutiveAssessment.model_validate(valid_assessment())
        formatted = assessment_for_board(assessment.model_dump_json())
        self.assertIn("[founder-provided]", formatted)
        self.assertIn("[assumption]", formatted)
        self.assertIn("LEGACY UNSTRUCTURED", assessment_for_board("old Markdown assessment"))
        self.assertIn("Decision gates", formatted)

    def test_assessment_checkpoint_compatibility_does_not_weaken_live_validation(self):
        prior_contract = valid_assessment()
        del prior_contract["decision_gates"]
        prior_content = json.dumps(prior_contract)

        restored, missing_fields = parse_assessment_checkpoint(prior_content)
        self.assertEqual(missing_fields, ["decision_gates"])
        self.assertEqual(restored.decision_gates, [])
        self.assertIn("predates decision_gates", assessment_for_board(prior_content))
        with self.assertRaises(ValueError):
            parse_structured_output(prior_content, ExecutiveAssessment)

    def test_executive_profiles_define_distinct_permanent_boundaries_and_criteria(self):
        self.assertEqual(set(EXECUTIVE_PROFILES), {"CEO", "CFO", "CTO", "CSO"})
        for role, profile in EXECUTIVE_PROFILES.items():
            with self.subTest(role=role):
                self.assertTrue(profile.areas_of_expertise)
                self.assertTrue(profile.responsibilities)
                self.assertTrue(profile.decision_boundaries)
                self.assertTrue(profile.expected_challenges)
                self.assertTrue(profile.evidence_limits)
                self.assertTrue(profile.evaluation_criteria)
                self.assertTrue(profile.relationships)
                self.assertTrue(profile.output_contract)
                prompt = executive_system_prompt(role, "phase test contract")
                self.assertIn(f"PROFILE v{EXECUTIVE_PROFILE_VERSION}", prompt)
                self.assertIn(profile.evidence_limits, prompt)
                self.assertIn("phase test contract", prompt)

    def test_position_extraction_assigns_stable_ids_and_preserves_dissent(self):
        assessments = {
            "CEO": valid_assessment_json("CEO", "proceed"),
            "CFO": valid_assessment_json("CFO", "defer"),
            "CTO": valid_assessment_json("CTO", "conditional"),
            "CSO": valid_assessment_json("CSO", "conditional"),
        }

        extraction = build_position_extraction(assessments)

        self.assertEqual(len(extraction.executives), 4)
        self.assertIn("CEO.decision_gates.1", {
            statement.claim_id
            for executive in extraction.executives
            for statement in executive.statements
        })
        self.assertEqual(extraction.executives[0].role, "CEO")
        self.assertIn("CEO=proceed", extraction.position_label_divergences[0])
        self.assertIn("CFO=defer", extraction.position_label_divergences[0])
        self.assertIn("Recommendation statements vary", extraction.recommendation_divergences[0])
        docket = format_challenge_docket(
            extraction,
            "CSO",
            EXECUTIVE_PROFILES["CSO"].challenge_categories,
        )
        self.assertIn("CEO.assumptions.1", docket)
        self.assertNotIn("--- CSO ---", docket)
        self.assertNotIn("- CEO.", docket)

    def test_position_extraction_flags_conflicting_evidence_classifications(self):
        assessments = {}
        for role, classification in (
            ("CEO", "verified"),
            ("CFO", "assumption"),
            ("CTO", "hypothesis"),
            ("CSO", "founder-provided"),
        ):
            payload = valid_assessment()
            payload["supporting_facts"] = [
                {
                    "claim": "The dataset has patient-level separation.",
                    "classification": classification,
                }
            ]
            assessments[role] = json.dumps(payload)

        extraction = build_position_extraction(assessments)

        self.assertEqual(len(extraction.claim_classification_divergences), 1)
        self.assertIn(
            "The executives classify the same claim differently",
            extraction.claim_classification_divergences[0],
        )

    def test_position_extraction_keeps_legacy_reports_explicitly_unstructured(self):
        assessments = {
            "CEO": "Legacy CEO recommendation and assumptions.",
            "CFO": valid_assessment_json("CFO"),
            "CTO": valid_assessment_json("CTO"),
            "CSO": valid_assessment_json("CSO"),
        }
        extraction = build_position_extraction(assessments)
        ceo = extraction.executives[0]
        self.assertFalse(ceo.is_structured)
        self.assertIn("Legacy CEO", ceo.legacy_assessment)
        self.assertIn("CEO.legacy_assessment", format_challenge_docket(
            extraction,
            "CFO",
            EXECUTIVE_PROFILES["CFO"].challenge_categories,
        ))

    def test_cross_examination_must_target_valid_peer_claims_exactly_once(self):
        extraction = build_position_extraction({
            role: valid_assessment_json(role)
            for role in ("CEO", "CFO", "CTO", "CSO")
        })
        valid = json.dumps(valid_cross_examination("CEO"))
        categories = EXECUTIVE_PROFILES["CEO"].challenge_categories
        parsed = parse_targeted_cross_examination(valid, "CEO", extraction, categories)
        self.assertEqual(len(parsed.challenges), 3)
        self.assertIn("CEO targeted cross-examination", format_targeted_cross_examination(
            valid,
            "CEO",
            extraction,
            categories,
        ))

        unknown_claim = valid_cross_examination("CEO")
        unknown_claim["challenges"][0]["target_claim_id"] = "CFO.uninvented.1"
        with self.assertRaisesRegex(ValueError, "not in CFO's docket"):
            parse_targeted_cross_examination(
                json.dumps(unknown_claim),
                "CEO",
                extraction,
                categories,
            )

        wrong_peers = valid_cross_examination("CEO")
        wrong_peers["challenges"][0]["target_role"] = "CTO"
        with self.assertRaisesRegex(ValueError, "one claim from each other"):
            parse_targeted_cross_examination(
                json.dumps(wrong_peers),
                "CEO",
                extraction,
                categories,
            )

        outside_docket = valid_cross_examination("CEO")
        outside_docket["challenges"][0]["target_claim_id"] = "CFO.decision_gates.1"
        with self.assertRaisesRegex(ValueError, "not in CFO's docket"):
            parse_targeted_cross_examination(
                json.dumps(outside_docket),
                "CEO",
                extraction,
                categories,
            )

    def test_challenges_validate_evidence_ids_and_dispute_subset(self):
        challenge = TargetedChallenge.model_validate({
            "target_role": "CFO",
            "target_claim_id": "CFO.assumptions.1",
            "challenge_question": "Does the evidence apply to this population?",
            "why_it_matters": "The estimate depends on transferability.",
            "source_evidence_ids": [12],
            "disputed_evidence_ids": [12],
        })
        self.assertEqual(challenge.disputed_evidence_ids, [12])
        with self.assertRaisesRegex(ValidationError, "must also be cited"):
            TargetedChallenge.model_validate({
                **challenge.model_dump(),
                "source_evidence_ids": [],
            })

    def test_verified_assessment_claim_requires_a_cited_attached_record(self):
        payload = valid_assessment()
        payload["supporting_facts"] = [{
            "claim": "This dataset has patient-level separation.",
            "classification": "verified",
            "source_evidence_ids": [41],
        }]
        assessment = ExecutiveAssessment.model_validate(payload)
        validate_assessment_evidence_references(assessment, {41}, "CSO")
        payload["supporting_facts"][0]["source_evidence_ids"] = []
        unreferenced = ExecutiveAssessment.model_validate(payload)
        with self.assertRaisesRegex(ValueError, "without citing"):
            validate_assessment_evidence_references(unreferenced, set(), "CSO")

    def test_revision_allows_maintain_revise_and_withdraw(self):
        maintained = PositionRevision.model_validate(
            valid_revision("maintain", "conditional", "conditional")
        )
        revised = PositionRevision.model_validate(
            valid_revision("revise", "proceed", "conditional")
        )
        withdrawn = PositionRevision.model_validate(
            valid_revision("withdraw", "reject", None)
        )
        self.assertEqual(maintained.revised_position, "conditional")
        self.assertEqual(revised.position_change, "revise")
        self.assertIsNone(withdrawn.revised_position)

    def test_revision_rejects_inconsistent_or_incomplete_transition(self):
        for revision in (
            valid_revision("maintain", "proceed", "reject"),
            valid_revision("revise", "defer", "defer"),
            valid_revision("withdraw", "reject", "conditional"),
            {
                **valid_revision("revise", "proceed", "conditional"),
                "remaining_disagreements": [{"claim": "Unclassified claim"}],
            },
        ):
            with self.subTest(revision=revision), self.assertRaises(ValidationError):
                PositionRevision.model_validate(revision)

    def test_revision_previous_position_must_match_structured_assessment(self):
        mismatched_revision = valid_revision("revise", "proceed", "conditional")
        original_assessment = valid_assessment()
        original_assessment["executive_position"] = "reject"

        with self.assertRaisesRegex(ValueError, "must match"):
            parse_revision_for_assessment(
                PositionRevision.model_validate(mismatched_revision).model_dump_json(),
                ExecutiveAssessment.model_validate(original_assessment).model_dump_json(),
            )

        legacy_revision = valid_revision("revise", "proceed", "conditional")
        self.assertEqual(
            parse_revision_for_assessment(
                PositionRevision.model_validate(legacy_revision).model_dump_json(),
                "Legacy assessment without a structured position.",
            ).previous_position,
            "proceed",
        )

    def test_board_markdown_preserves_dissent_and_evidence_status(self):
        synthesis = BoardSynthesis.model_validate({
            "schema_version": 1,
            "executive_summary": "Proceed only with a bounded discovery phase.",
            "recommendation": "Approve the discovery phase, not product launch.",
            "rationale": "The available evidence is early and incomplete.",
            "shared_conclusions": ["More evidence is needed."],
            "genuine_disagreements": ["CEO supports a pilot; CFO recommends deferral."],
            "material_dissent": ["CSO rejects any clinical claim before validation."],
            "evidence_register": [
                {
                    "claim": "The founder stated the initial focus.",
                    "classification": "founder-provided",
                    "source_role": "CEO",
                },
                {
                    "claim": "Clinics will pay for the product.",
                    "classification": "assumption",
                    "source_role": "CFO",
                },
            ],
            "unresolved_questions": ["Will clinics participate?"],
            "next_actions": [
                {
                    "action": "Interview clinic staff.",
                    "owner": "CEO",
                    "success_criteria": ["10 completed interviews"],
                    "decision_gate": "Before any pilot spend.",
                }
            ],
            "decision_gates": ["Do not claim clinical validity before external validation."],
        })

        markdown = board_synthesis_markdown(synthesis)

        self.assertIn("## Genuine disagreements", markdown)
        self.assertIn("CEO supports a pilot; CFO recommends deferral.", markdown)
        self.assertIn("[founder-provided · CEO]", markdown)
        self.assertIn("[assumption · CFO]", markdown)
        self.assertIn("## Material dissent", markdown)
        self.assertIn("## Decision gates", markdown)

    def test_board_parser_rejects_malformed_or_incomplete_output(self):
        for content in (
            "not JSON",
            '{"schema_version":1,"executive_summary":"Incomplete"}',
        ):
            with self.subTest(content=content), self.assertRaises(ValueError):
                parse_structured_output(content, BoardSynthesis)


if __name__ == "__main__":
    unittest.main()
