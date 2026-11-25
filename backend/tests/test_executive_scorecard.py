import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import get_current_user
from app.company import ensure_company
from app.database import Base, get_db
from app.models import AgentContribution, BoardMeeting, MeetingRunCheckpoint, MeetingStatus
from app.routers import performance


def structured_assessment_json():
    return json.dumps(
        {
            "schema_version": 1,
            "executive_position": "conditional",
            "recommendation": (
                "Proceed with a bounded pilot and measure detection latency over 20 cases."
            ),
            "confidence": "medium",
            "supporting_facts": [
                {
                    "claim": "The pilot cohort showed median detection latency of 12 seconds.",
                    "classification": "verified",
                    "source_evidence_ids": [1],
                }
            ],
            "assumptions": [
                {
                    "claim": "Two hospital partners will provide data within 60 days.",
                    "classification": "assumption",
                    "source_evidence_ids": [],
                }
            ],
            "hypotheses": [
                {
                    "claim": "Detection accuracy improves with additional channels.",
                    "classification": "hypothesis",
                    "source_evidence_ids": [],
                }
            ],
            "unknowns": [
                {
                    "claim": "The regulatory class is not yet confirmed.",
                    "classification": "unknown",
                    "source_evidence_ids": [],
                }
            ],
            "risks": [
                {
                    "claim": "Dataset access may slip by a quarter.",
                    "classification": "assumption",
                    "source_evidence_ids": [],
                }
            ],
            "alternatives": [
                {
                    "claim": "Defer until dataset access is signed.",
                    "classification": "assumption",
                    "source_evidence_ids": [],
                }
            ],
            "dependencies": [],
            "success_criteria": [
                {
                    "claim": "Median detection latency under 15 seconds across 20 cases.",
                    "classification": "estimate",
                    "source_evidence_ids": [],
                }
            ],
            "decision_gates": [
                {
                    "claim": "Do not build beyond pilot until 20 cases are reviewed.",
                    "classification": "assumption",
                    "source_evidence_ids": [],
                }
            ],
        }
    )


def structured_challenge_json():
    roles = [
        ("CFO", "The pilot budget is not tied to a stop condition."),
        ("CTO", "The integration plan ignores site security review."),
        ("CSO", "Twenty cases cannot establish clinical validity."),
    ]
    return json.dumps(
        {
            "schema_version": 1,
            "challenges": [
                {
                    "target_role": role,
                    "target_claim_id": f"{role}.recommendation",
                    "challenge_question": (
                        f"What evidence shows that {role} can support this commitment "
                        "within the current stage?"
                    ),
                    "why_it_matters": (
                        "If this commitment is unsupported, the pilot could consume the "
                        "remaining runway before any evidence is produced."
                    ),
                    "source_evidence_ids": [1],
                    "disputed_evidence_ids": [],
                }
                for role, _ in roles
            ],
        }
    )


def structured_revision_json():
    return json.dumps(
        {
            "schema_version": 1,
            "position_change": "revise",
            "previous_position": "conditional",
            "revised_position": "proceed",
            "reason_for_change": (
                "The CFO showed that the pilot has a hard stop condition, so a bounded "
                "proceed is safer than waiting without data."
            ),
            "arguments_that_changed_my_view": [
                {
                    "claim": "A stop condition caps downside spend.",
                    "classification": "founder-provided",
                    "source_evidence_ids": [1],
                }
            ],
            "remaining_disagreements": [],
        }
    )


class ExecutiveScorecardTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "scorecard.db"
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        _seed = self.session_factory()
        self.company_id = ensure_company(_seed).id
        _seed.close()

        app = FastAPI()
        app.include_router(performance.router)
        app.dependency_overrides[get_current_user] = lambda: {"sub": "founder"}
        app.dependency_overrides[get_db] = self._override_db
        self.client = TestClient(app)

    def _override_db(self):
        db = self.session_factory()
        try:
            yield db
        finally:
            db.close()

    def tearDown(self):
        self.engine.dispose()
        self.temp_dir.cleanup()

    def _meeting_with_contribution(self, role="CEO"):
        db = self.session_factory()
        try:
            meeting = BoardMeeting(
                company_id=self.company_id,
                title="Seizure detection pilot",
                agenda="Proceed with the pilot?",
                founder_context="Dataset access is pending.",
                status=MeetingStatus.completed,
            )
            db.add(meeting)
            db.commit()
            db.refresh(meeting)
            contribution = AgentContribution(
                meeting_id=meeting.id,
                role=role,
                phase="assessment",
                assessment=structured_assessment_json(),
                critique=structured_challenge_json(),
                model_provider="local",
                model_name="qwen",
            )
            db.add(contribution)
            db.add(
                MeetingRunCheckpoint(
                    meeting_id=meeting.id,
                    phase="revision",
                    role=role,
                    content=structured_revision_json(),
                    model_provider="local",
                    model_name="qwen",
                )
            )
            db.commit()
            db.refresh(contribution)
            return meeting.id, contribution.id
        finally:
            db.close()

    def _rate(self, role, dimension, rating, meeting_id, contribution_id=None):
        return self.client.post(
            "/api/performance/feedback",
            json={
                "role": role,
                "dimension": dimension,
                "rating": rating,
                "meeting_id": meeting_id,
                "contribution_id": contribution_id,
                "notes": "Founder judgement.",
            },
        )

    def test_scorecard_exposes_seven_quality_metrics_and_no_agreement_metric(self):
        meeting_id, contribution_id = self._meeting_with_contribution()
        self.assertEqual(self._rate("CEO", "decision_usefulness", 5, meeting_id, contribution_id).status_code, 200)
        self.assertEqual(self._rate("CEO", "forecast_accuracy", 4, meeting_id).status_code, 200)

        response = self.client.get("/api/performance")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["scorecards"]), 4)
        ceo = next(card for card in body["scorecards"] if card["role"] == "CEO")
        keys = {metric["key"] for metric in ceo["metrics"]}
        self.assertEqual(
            keys,
            {
                "evidence_discipline",
                "mandate_adherence",
                "challenge_quality",
                "position_integrity",
                "specificity",
                "forecast_accuracy",
                "decision_usefulness",
            },
        )
        self.assertNotIn("agreement", keys)
        self.assertNotIn("alignment", keys)
        metrics = {metric["key"]: metric for metric in ceo["metrics"]}
        self.assertGreaterEqual(metrics["evidence_discipline"]["score"], 80)
        self.assertGreaterEqual(metrics["challenge_quality"]["score"], 80)
        self.assertGreaterEqual(metrics["specificity"]["score"], 60)
        self.assertEqual(metrics["decision_usefulness"]["score"], 100)
        self.assertEqual(metrics["forecast_accuracy"]["score"], 75)
        self.assertEqual(metrics["decision_usefulness"]["sample_size"], 1)
        self.assertIn("agreement", metrics["decision_usefulness"]["note"].lower())
        self.assertIsNotNone(ceo["overall_score"])
        self.assertEqual(ceo["contributions"], 1)
        self.assertEqual(ceo["feedback_count"], 2)
        self.assertIn("agreement", body["feedback_policy"]["excluded_signal"].lower())
        self.assertEqual(len(body["metric_definitions"]), 7)

    def test_feedback_is_upserted_per_meeting_role_and_dimension(self):
        meeting_id, contribution_id = self._meeting_with_contribution()
        first = self._rate("CEO", "decision_usefulness", 5, meeting_id, contribution_id)
        self.assertEqual(first.status_code, 200)
        second = self._rate("CEO", "decision_usefulness", 3, meeting_id, contribution_id)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["id"], second.json()["id"])

        reviews = self.client.get("/api/performance/contributions", params={"role": "CEO"})
        self.assertEqual(reviews.status_code, 200)
        body = reviews.json()
        self.assertEqual(len(body), 1)
        self.assertEqual(len(body[0]["feedback"]), 1)
        self.assertEqual(body[0]["feedback"][0]["rating"], 3)
        self.assertIn("bounded pilot", body[0]["assessment_excerpt"].lower())

        score = self.client.get("/api/performance").json()
        ceo = next(card for card in score["scorecards"] if card["role"] == "CEO")
        metric = next(
            item for item in ceo["metrics"] if item["key"] == "decision_usefulness"
        )
        self.assertEqual(metric["score"], 50)

    def test_feedback_rejects_out_of_range_rating_and_wrong_role(self):
        meeting_id, contribution_id = self._meeting_with_contribution()
        self.assertEqual(
            self._rate("CEO", "decision_usefulness", 6, meeting_id).status_code,
            422,
        )
        response = self._rate("CFO", "decision_usefulness", 4, meeting_id, contribution_id)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            self._rate("CFO", "unknown_dimension", 4, meeting_id).status_code,
            422,
        )


if __name__ == "__main__":
    unittest.main()
