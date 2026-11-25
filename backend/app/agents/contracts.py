import json
import re
from typing import Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


ExecutivePosition = Literal["proceed", "reject", "defer", "conditional"]
ExecutiveRole = Literal["CEO", "CFO", "CTO", "CSO"]
ClaimClassification = Literal[
    "verified",
    "founder-provided",
    "assumption",
    "estimate",
    "hypothesis",
    "unknown",
]
EXECUTIVE_ROLES = ("CEO", "CFO", "CTO", "CSO")
CLAIM_CATEGORIES = (
    "supporting_facts",
    "assumptions",
    "hypotheses",
    "unknowns",
    "risks",
    "alternatives",
    "dependencies",
    "success_criteria",
    "decision_gates",
)

PositionStatementCategory = Literal[
    "executive_position",
    "recommendation",
    "supporting_facts",
    "assumptions",
    "hypotheses",
    "unknowns",
    "risks",
    "alternatives",
    "dependencies",
    "success_criteria",
    "decision_gates",
]


class TaggedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: str = Field(min_length=1)
    classification: ClaimClassification
    source_evidence_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_evidence_ids(self):
        if any(evidence_id <= 0 for evidence_id in self.source_evidence_ids):
            raise ValueError("Evidence record IDs must be positive integers.")
        if len(set(self.source_evidence_ids)) != len(self.source_evidence_ids):
            raise ValueError("Evidence record IDs must be unique.")
        return self


class ExecutiveAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    executive_position: ExecutivePosition
    recommendation: str = Field(min_length=1)
    confidence: Literal["low", "medium", "high"]
    supporting_facts: list[TaggedClaim]
    assumptions: list[TaggedClaim]
    hypotheses: list[TaggedClaim]
    unknowns: list[TaggedClaim]
    risks: list[TaggedClaim]
    alternatives: list[TaggedClaim]
    dependencies: list[TaggedClaim]
    success_criteria: list[TaggedClaim]
    decision_gates: list[TaggedClaim]


class PositionStatement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(min_length=1)
    category: PositionStatementCategory
    statement: str = Field(min_length=1)
    classification: ClaimClassification | None = None
    source_evidence_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_classification(self):
        if self.category in CLAIM_CATEGORIES and self.classification is None:
            raise ValueError(f"{self.category} statements require a claim classification.")
        if self.category not in CLAIM_CATEGORIES and self.classification is not None:
            raise ValueError(
                f"{self.category} statements must not be assigned an evidence classification."
            )
        return self


class ExtractedExecutivePosition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: ExecutiveRole
    is_structured: bool
    executive_position: ExecutivePosition | None
    recommendation: str | None
    confidence: Literal["low", "medium", "high"] | None
    statements: list[PositionStatement]
    legacy_assessment: str | None = None
    compatibility_missing_fields: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_source_shape(self):
        if self.is_structured:
            if (
                self.executive_position is None
                or not self.recommendation
                or self.confidence is None
                or self.legacy_assessment is not None
            ):
                raise ValueError("Structured positions require their validated assessment fields.")
        elif not self.legacy_assessment:
            raise ValueError("Legacy positions require their original unstructured assessment.")
        return self


class PositionExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    executives: list[ExtractedExecutivePosition] = Field(min_length=4, max_length=4)
    position_label_divergences: list[str]
    recommendation_divergences: list[str]
    claim_classification_divergences: list[str]

    @model_validator(mode="after")
    def validate_executive_roles(self):
        roles = [executive.role for executive in self.executives]
        if set(roles) != set(EXECUTIVE_ROLES) or len(roles) != len(set(roles)):
            raise ValueError("Position extraction must contain exactly one record per executive.")
        return self


class TargetedChallenge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_role: ExecutiveRole
    target_claim_id: str = Field(min_length=1)
    challenge_question: str = Field(min_length=1)
    why_it_matters: str = Field(min_length=1)
    source_evidence_ids: list[int] = Field(default_factory=list)
    disputed_evidence_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_evidence_ids(self):
        if any(
            evidence_id <= 0
            for evidence_id in self.source_evidence_ids + self.disputed_evidence_ids
        ):
            raise ValueError("Evidence record IDs must be positive integers.")
        if len(set(self.source_evidence_ids)) != len(self.source_evidence_ids):
            raise ValueError("Evidence record IDs must be unique.")
        if len(set(self.disputed_evidence_ids)) != len(self.disputed_evidence_ids):
            raise ValueError("Disputed evidence record IDs must be unique.")
        if not set(self.disputed_evidence_ids).issubset(self.source_evidence_ids):
            raise ValueError("Disputed evidence IDs must also be cited by the challenge.")
        return self


class ExecutiveCrossExamination(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    challenges: list[TargetedChallenge] = Field(min_length=3, max_length=3)


class PositionRevision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    position_change: Literal["maintain", "revise", "withdraw"]
    previous_position: ExecutivePosition
    revised_position: ExecutivePosition | None
    reason_for_change: str = Field(min_length=1)
    arguments_that_changed_my_view: list[TaggedClaim]
    remaining_disagreements: list[TaggedClaim]

    @model_validator(mode="after")
    def validate_position_transition(self):
        if self.position_change == "withdraw":
            if self.revised_position is not None:
                raise ValueError("A withdrawn position must have revised_position set to null.")
        elif self.revised_position is None:
            raise ValueError("A maintained or revised position requires revised_position.")
        elif self.position_change == "maintain" and self.revised_position != self.previous_position:
            raise ValueError("A maintained position must equal previous_position.")
        elif self.position_change == "revise" and self.revised_position == self.previous_position:
            raise ValueError("A revised position must differ from previous_position.")
        return self


class BoardEvidenceClaim(TaggedClaim):
    source_role: Literal["CEO", "CFO", "CTO", "CSO"]


class BoardAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    success_criteria: list[str]
    decision_gate: str = Field(min_length=1)


class BoardSynthesis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    executive_summary: str = Field(min_length=1)
    recommendation: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    shared_conclusions: list[str]
    genuine_disagreements: list[str]
    material_dissent: list[str]
    evidence_register: list[BoardEvidenceClaim]
    unresolved_questions: list[str]
    next_actions: list[BoardAction]
    decision_gates: list[str]


def validate_claim_evidence_references(
    claims: list[TaggedClaim],
    available_evidence_ids: set[int],
    role: str,
    phase: str,
) -> None:
    for claim in claims:
        unknown_ids = set(claim.source_evidence_ids) - available_evidence_ids
        if unknown_ids:
            raise ValueError(
                f"{role} {phase} references evidence IDs not attached to this meeting: "
                + ", ".join(map(str, sorted(unknown_ids)))
            )
        if claim.classification == "verified" and not claim.source_evidence_ids:
            raise ValueError(
                f"{role} {phase} classified a claim as verified without citing a meeting evidence record."
            )


def validate_assessment_evidence_references(
    assessment: ExecutiveAssessment,
    available_evidence_ids: set[int],
    role: str,
) -> None:
    validate_claim_evidence_references(
        [
            claim
            for field in CLAIM_CATEGORIES
            for claim in getattr(assessment, field)
        ],
        available_evidence_ids,
        role,
        "assessment",
    )


def validate_board_evidence_references(
    synthesis: BoardSynthesis,
    available_evidence_ids: set[int],
) -> None:
    validate_claim_evidence_references(
        synthesis.evidence_register,
        available_evidence_ids,
        "BOARD",
        "synthesis",
    )


StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


def parse_structured_output(content: str, model_type: type[StructuredModel]) -> StructuredModel:
    candidate = content.strip()
    if candidate.startswith("```"):
        match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", candidate, re.IGNORECASE | re.DOTALL)
        if not match:
            raise ValueError(f"{model_type.__name__} output has an incomplete JSON code fence.")
        candidate = match.group(1).strip()
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{model_type.__name__} output must be a single valid JSON object: {exc.msg}."
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{model_type.__name__} output must be a JSON object.")
    try:
        return model_type.model_validate(payload)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        raise ValueError(
            f"{model_type.__name__} output is invalid or incomplete: {details}"
        ) from exc


def parse_assessment_checkpoint(content: str) -> tuple[ExecutiveAssessment, list[str]]:
    try:
        return parse_structured_output(content, ExecutiveAssessment), []
    except ValueError as strict_error:
        candidate = content.strip()
        if candidate.startswith("```"):
            match = re.fullmatch(
                r"```(?:json)?\s*(.*?)\s*```",
                candidate,
                re.IGNORECASE | re.DOTALL,
            )
            if not match:
                raise strict_error
            candidate = match.group(1).strip()
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            raise strict_error
        previous_contract_fields = set(ExecutiveAssessment.model_fields) - {
            "decision_gates"
        }
        if (
            not isinstance(payload, dict)
            or set(payload) != previous_contract_fields
            or payload.get("schema_version") != 1
        ):
            raise strict_error
        try:
            assessment = ExecutiveAssessment.model_validate({
                **payload,
                "decision_gates": [],
            })
        except ValidationError:
            raise strict_error
        return assessment, ["decision_gates"]


def _format_claims(label: str, claims: list[TaggedClaim]) -> str:
    if not claims:
        return f"{label}: none stated"
    lines = [f"{label}:"]
    lines.extend(
        f"- [{item.classification}] {item.claim}"
        + (
            f" (evidence IDs: {', '.join(map(str, item.source_evidence_ids))})"
            if item.source_evidence_ids
            else ""
        )
        for item in claims
    )
    return "\n".join(lines)


def parse_revision_for_assessment(
    revision_content: str,
    assessment_content: str,
) -> PositionRevision:
    revision = parse_structured_output(revision_content, PositionRevision)
    candidate = assessment_content.strip()
    json_fence = re.match(r"^```json(?:\s|$)", candidate, re.IGNORECASE)
    if candidate.startswith("{") or json_fence:
        assessment, _ = parse_assessment_checkpoint(assessment_content)
        if revision.previous_position != assessment.executive_position:
            raise ValueError(
                "PositionRevision output is invalid: previous_position must match "
                "the executive's original assessment."
            )
    return revision


def _looks_like_structured_json(content: str) -> bool:
    candidate = content.strip()
    return candidate.startswith("{") or bool(
        re.match(r"^```json(?:\s|$)", candidate, re.IGNORECASE)
    )


def build_position_extraction(assessments: dict[str, str]) -> PositionExtraction:
    missing_roles = [role for role in EXECUTIVE_ROLES if not assessments.get(role)]
    if missing_roles:
        raise ValueError(
            "Cannot extract executive positions without assessments for: "
            + ", ".join(missing_roles)
        )

    extracted = []
    for role in EXECUTIVE_ROLES:
        content = assessments[role]
        if not _looks_like_structured_json(content):
            preview = content.strip()
            if len(preview) > 1600:
                preview = (
                    f"{preview[:1050]}\n[legacy assessment excerpt omitted]\n{preview[-400:]}"
                )
            extracted.append(ExtractedExecutivePosition(
                role=role,
                is_structured=False,
                executive_position=None,
                recommendation=None,
                confidence=None,
                statements=[],
                legacy_assessment=preview,
            ))
            continue

        assessment, compatibility_missing_fields = parse_assessment_checkpoint(content)
        statements = [
            PositionStatement(
                claim_id=f"{role}.executive_position",
                category="executive_position",
                statement=assessment.executive_position,
            ),
            PositionStatement(
                claim_id=f"{role}.recommendation",
                category="recommendation",
                statement=assessment.recommendation,
            ),
        ]
        for category in CLAIM_CATEGORIES:
            statements.extend(
                PositionStatement(
                    claim_id=f"{role}.{category}.{index}",
                    category=category,
                    statement=claim.claim,
                    classification=claim.classification,
                    source_evidence_ids=claim.source_evidence_ids,
                )
                for index, claim in enumerate(getattr(assessment, category), start=1)
            )
        extracted.append(ExtractedExecutivePosition(
            role=role,
            is_structured=True,
            executive_position=assessment.executive_position,
            recommendation=assessment.recommendation,
            confidence=assessment.confidence,
            statements=statements,
            compatibility_missing_fields=compatibility_missing_fields,
        ))

    positions = [
        (executive.role, executive.executive_position)
        for executive in extracted
        if executive.is_structured
    ]
    distinct_positions = {position for _, position in positions}
    position_divergences = []
    if len(distinct_positions) > 1:
        position_divergences.append(
            "Executive position labels differ: "
            + "; ".join(f"{role}={position}" for role, position in positions)
            + ". Aligned labels do not imply agreement on evidence or recommendations."
        )
    recommendations = [
        (executive.role, executive.recommendation)
        for executive in extracted
        if executive.is_structured and executive.recommendation
    ]
    normalized_recommendations = {
        re.sub(r"\s+", " ", recommendation).strip().casefold()
        for _, recommendation in recommendations
    }
    recommendation_divergences = []
    if len(normalized_recommendations) > 1:
        recommendation_divergences.append(
            "Recommendation statements vary; evaluate whether the difference is "
            "substantive rather than assuming conflict: "
            + "; ".join(f"{role}={recommendation}" for role, recommendation in recommendations)
            + "."
        )

    classifications_by_claim: dict[str, list[tuple[str, ClaimClassification]]] = {}
    statement_text_by_claim = {}
    for executive in extracted:
        for statement in executive.statements:
            if statement.category not in CLAIM_CATEGORIES or statement.classification is None:
                continue
            normalized_claim = re.sub(r"\s+", " ", statement.statement).strip().casefold()
            classifications_by_claim.setdefault(normalized_claim, []).append(
                (executive.role, statement.classification)
            )
            statement_text_by_claim[normalized_claim] = statement.statement
    classification_divergences = []
    for normalized_claim, role_classifications in classifications_by_claim.items():
        if (
            len(role_classifications) > 1
            and len({classification for _, classification in role_classifications}) > 1
        ):
            classification_divergences.append(
                "The executives classify the same claim differently: "
                f"'{statement_text_by_claim[normalized_claim]}' — "
                + "; ".join(
                    f"{role}={classification}"
                    for role, classification in role_classifications
                )
                + "."
            )
    return PositionExtraction(
        schema_version=1,
        executives=extracted,
        position_label_divergences=position_divergences,
        recommendation_divergences=recommendation_divergences,
        claim_classification_divergences=classification_divergences,
    )


def _docket_statements(
    executive: ExtractedExecutivePosition,
    challenge_categories: tuple[str, ...],
    max_claims_per_role: int,
) -> list[PositionStatement]:
    selected = [
        statement
        for category in challenge_categories
        for statement in executive.statements
        if statement.category == category
    ][:max_claims_per_role]
    if not selected:
        selected = [
            statement
            for statement in executive.statements
            if statement.category not in {"executive_position", "recommendation"}
        ][:max_claims_per_role]
    return selected


def _docket_claim_ids(
    executive: ExtractedExecutivePosition,
    challenge_categories: tuple[str, ...],
    max_claims_per_role: int,
) -> set[str]:
    if not executive.is_structured:
        return {f"{executive.role}.legacy_assessment"}
    return {
        f"{executive.role}.executive_position",
        f"{executive.role}.recommendation",
        *(
            statement.claim_id
            for statement in _docket_statements(
                executive,
                challenge_categories,
                max_claims_per_role,
            )
        ),
    }


def format_challenge_docket(
    extraction: PositionExtraction,
    challenger_role: str,
    challenge_categories: tuple[str, ...],
    max_claims_per_role: int = 4,
    evidence_records: list[dict] | None = None,
) -> str:
    lines = [
        "DISAGREEMENT CANDIDATES FROM POSITION EXTRACTION:",
        *(
            f"- {item}"
            for item in extraction.position_label_divergences
        ),
        *(
            f"- {item}"
            for item in extraction.recommendation_divergences
        ),
        *(
            f"- {item}"
            for item in extraction.claim_classification_divergences
        ),
    ]
    if not (
        extraction.position_label_divergences
        or extraction.recommendation_divergences
        or extraction.claim_classification_divergences
    ):
        lines.append(
            "- No deterministic disagreement candidate detected; this is not evidence "
            "of agreement."
        )

    if evidence_records:
        lines.extend(("", "--- SOURCE-BACKED EVIDENCE REGISTER ---"))
        for record in evidence_records:
            lines.append(
                f"- Evidence ID `EVIDENCE-{record['id']}` · "
                f"[{record['classification']} · {record['category']} · "
                f"quality {record['evidence_quality']}] {record['claim']}"
            )
            if record.get("source_title") or record.get("source_url"):
                lines.append(
                    f"  Source: {record.get('source_title') or 'Untitled'} "
                    f"{record.get('source_url') or ''}".strip()
                )
            lines.append(
                f"  Limitations: {record.get('limitations') or 'Not assessed.'}"
            )

    for executive in extraction.executives:
        if executive.role == challenger_role:
            continue
        lines.extend(("", f"--- {executive.role} ---"))
        if not executive.is_structured:
            lines.append(f"- `{executive.role}.legacy_assessment` [unstructured]:")
            lines.append(executive.legacy_assessment or "No legacy assessment text.")
            continue

        if executive.compatibility_missing_fields:
            lines.append(
                "- Compatibility note: the saved assessment predates "
                + ", ".join(executive.compatibility_missing_fields)
                + "; no missing gate is inferred."
            )
        lines.append(f"- Position: {executive.executive_position}")
        lines.append(f"- Recommendation: {executive.recommendation}")
        lines.append(f"- Confidence: {executive.confidence}")
        selected = _docket_statements(
            executive,
            challenge_categories,
            max_claims_per_role,
        )
        for statement in selected:
            classification = (
                f" [{statement.classification}]"
                if statement.classification
                else ""
            )
            evidence = (
                f" (evidence IDs: {', '.join(map(str, statement.source_evidence_ids))})"
                if statement.source_evidence_ids
                else ""
            )
            lines.append(
                f"- `{statement.claim_id}`{classification}{evidence}: {statement.statement}"
            )
        if not selected:
            lines.append("- No classified claims available to target.")
    return "\n".join(lines)


def parse_targeted_cross_examination(
    content: str,
    challenger_role: str,
    extraction: PositionExtraction,
    challenge_categories: tuple[str, ...],
    max_claims_per_role: int = 4,
    available_evidence_ids: set[int] | None = None,
) -> ExecutiveCrossExamination | None:
    if not _looks_like_structured_json(content):
        return None
    examination = parse_structured_output(content, ExecutiveCrossExamination)
    expected_targets = set(EXECUTIVE_ROLES) - {challenger_role}
    actual_targets = [item.target_role for item in examination.challenges]
    if set(actual_targets) != expected_targets or len(actual_targets) != len(expected_targets):
        raise ValueError(
            "ExecutiveCrossExamination must target exactly one claim from each other executive."
        )

    executives = {item.role: item for item in extraction.executives}
    for challenge in examination.challenges:
        target = executives[challenge.target_role]
        valid_claim_ids = _docket_claim_ids(
            target,
            challenge_categories,
            max_claims_per_role,
        )
        if challenge.target_claim_id not in valid_claim_ids:
            raise ValueError(
                f"ExecutiveCrossExamination references claim "
                f"'{challenge.target_claim_id}' that is not in {challenge.target_role}'s docket."
            )
        if available_evidence_ids is not None and not set(
            challenge.source_evidence_ids
        ).issubset(available_evidence_ids):
            raise ValueError(
                f"ExecutiveCrossExamination for {challenge.target_role} references an "
                "evidence record that is not attached to this meeting."
            )
    return examination


def format_targeted_cross_examination(
    content: str,
    challenger_role: str,
    extraction: PositionExtraction,
    challenge_categories: tuple[str, ...],
    available_evidence_ids: set[int] | None = None,
) -> str:
    examination = parse_targeted_cross_examination(
        content,
        challenger_role,
        extraction,
        challenge_categories,
        available_evidence_ids=available_evidence_ids,
    )
    if examination is None:
        return (
            "LEGACY UNSTRUCTURED CHALLENGE (not claim-validated):\n"
            f"{content}"
        )

    executives = {item.role: item for item in extraction.executives}
    rendered = []
    for challenge in examination.challenges:
        target = executives[challenge.target_role]
        statement = next(
            (
                item
                for item in target.statements
                if item.claim_id == challenge.target_claim_id
            ),
            None,
        )
        if statement is not None:
            classification = (
                f" [{statement.classification}]"
                if statement.classification
                else ""
            )
            target_text = f"{statement.statement}{classification}"
        else:
            target_text = target.legacy_assessment or "Legacy assessment text unavailable."
        rendered.append(
            f"- **{challenge.target_role} · `{challenge.target_claim_id}`**: "
            f"{target_text}\n"
            f"  - Challenge: {challenge.challenge_question}\n"
            f"  - Why it matters: {challenge.why_it_matters}\n"
            f"  - Evidence records considered: "
            f"{', '.join(f'`EVIDENCE-{item}`' for item in challenge.source_evidence_ids) or 'none'}\n"
            f"  - Evidence records disputed: "
            f"{', '.join(f'`EVIDENCE-{item}`' for item in challenge.disputed_evidence_ids) or 'none'}"
        )
    return "\n".join((
        f"## {challenger_role} targeted cross-examination",
        *rendered,
    ))


def assessment_for_board(content: str) -> str:
    candidate = content.strip()
    json_fence = re.match(r"^```json(?:\s|$)", candidate, re.IGNORECASE)
    if not candidate.startswith("{") and not json_fence:
        return f"LEGACY UNSTRUCTURED ASSESSMENT (not schema-validated):\n{content}"
    assessment, compatibility_missing_fields = parse_assessment_checkpoint(content)
    lines = [
        f"Position: {assessment.executive_position}",
        f"Recommendation: {assessment.recommendation}",
        f"Confidence: {assessment.confidence}",
    ]
    if compatibility_missing_fields:
        lines.append(
            "Compatibility note: saved assessment predates "
            + ", ".join(compatibility_missing_fields)
            + "; none are inferred."
        )
    for field, label in (
        ("supporting_facts", "Supporting facts"),
        ("assumptions", "Assumptions"),
        ("hypotheses", "Hypotheses"),
        ("unknowns", "Unknowns"),
        ("risks", "Risks"),
        ("alternatives", "Alternatives"),
        ("dependencies", "Dependencies"),
        ("success_criteria", "Success criteria"),
        ("decision_gates", "Decision gates"),
    ):
        lines.append(_format_claims(label, getattr(assessment, field)))
    return "\n".join(lines)


def revision_for_board(content: str) -> str:
    if not content.strip():
        return "No position revision is available."
    revision = parse_structured_output(content, PositionRevision)
    lines = [
        f"Position change: {revision.position_change}",
        f"Previous position: {revision.previous_position}",
        f"Revised position: {revision.revised_position or 'withdrawn'}",
        f"Reason for change: {revision.reason_for_change}",
        _format_claims("Arguments that changed the view", revision.arguments_that_changed_my_view),
        _format_claims("Remaining disagreements", revision.remaining_disagreements),
    ]
    return "\n".join(lines)


def board_synthesis_markdown(synthesis: BoardSynthesis) -> str:
    def bullet_section(title: str, items: list[str]) -> str:
        body = "\n".join(f"- {item}" for item in items) if items else "- None identified."
        return f"## {title}\n{body}"

    evidence = (
        "\n".join(
            f"- [{item.classification} · {item.source_role}] {item.claim}"
            + (
                " (evidence records: "
                + ", ".join(f"EVIDENCE-{evidence_id}" for evidence_id in item.source_evidence_ids)
                + ")"
                if item.source_evidence_ids
                else ""
            )
            for item in synthesis.evidence_register
        )
        or "- No claims classified."
    )
    actions = (
        "\n".join(
            f"- **{item.action}** — Owner: {item.owner}. "
            f"Success criteria: {', '.join(item.success_criteria) or 'to be defined'}. "
            f"Decision gate: {item.decision_gate}"
            for item in synthesis.next_actions
        )
        or "- None proposed."
    )
    return "\n\n".join((
        f"# Executive summary\n{synthesis.executive_summary}",
        f"## Proposed board recommendation\n{synthesis.recommendation}",
        f"## Rationale\n{synthesis.rationale}",
        bullet_section("Shared conclusions", synthesis.shared_conclusions),
        bullet_section("Genuine disagreements", synthesis.genuine_disagreements),
        bullet_section("Material dissent", synthesis.material_dissent),
        f"## Evidence classification\n{evidence}",
        bullet_section("Unresolved questions", synthesis.unresolved_questions),
        f"## Recommended next actions\n{actions}",
        bullet_section("Decision gates", synthesis.decision_gates),
        "**Founder authority:** This is a recommendation, not an approval. The founder records the decision.",
    ))


def board_dissent_markdown(synthesis: BoardSynthesis) -> str:
    sections = (
        ("Genuine disagreements", synthesis.genuine_disagreements),
        ("Material dissent", synthesis.material_dissent),
        ("Unresolved questions", synthesis.unresolved_questions),
    )
    return "\n\n".join(
        f"## {title}\n" + ("\n".join(f"- {item}" for item in items) or "- None identified.")
        for title, items in sections
    )
