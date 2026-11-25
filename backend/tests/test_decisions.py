import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import get_current_user
from app.company import ensure_company
from app.database import Base, get_db
from app.models import (
    BoardMeeting,
    BoardResolution,
    DecisionLifecycle,
    DecisionRecord,
    MeetingRunCheckpoint,
    DecisionStatus,
)
from app.routers import decisions, meetings as meeting_routes
from app.memory import is_review_due


def _resolution(meeting_id: int, status: DecisionStatus = DecisionStatus.approved) -> BoardResolution:
    return BoardResolution(
        meeting_id=meeting_id,
        recommendation="Board recommends a bounded seizure-detection pilot with one hospital partner.",
        rationale="The pilot tests demand and feasibility before a larger commitment.",
        dissent_and_open_questions="CFO flagged budget exposure.",
        decision_status=status,
        founder_notes="Proceed, but only with quarterly budget review.",
    )


class DecisionRegisterTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "decisions.db"
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
        app.include_router(decisions.router)
        app.include_router(meeting_routes.router)
        app.dependency_overrides[get_current_user] = lambda: {"sub": "founder"}

        def override_db():
            db = self.session_factory()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_db
        self.client = TestClient(app)

    def tearDown(self):
        self.engine.dispose()
        self.temp_dir.cleanup()

    def _create_meeting_with_resolution(self, title="Seizure detection conclave"):
        db = self.session_factory()
        try:
            meeting = BoardMeeting(
                company_id=self.company_id,
                title=title,
                agenda="Should we commit to a seizure detection pilot with a hospital partner?",
                founder_context="Two hospitals expressed interest; dataset access is pending.",
            )
            db.add(meeting)
            db.flush()
            db.add(_resolution(meeting.id))
            db.commit()
            return meeting.id
        finally:
            db.close()

    def test_founder_decree_auto_creates_decision_record(self):
        meeting_id = self._create_meeting_with_resolution()
        response = self.client.post(
            f"/api/meetings/{meeting_id}/decision",
            json={"action": "approve", "comments": "Proceed with quarterly budget review.", "actor": "Founder"},
        )
        self.assertEqual(response.status_code, 200)

        db = self.session_factory()
        try:
            record = db.query(DecisionRecord).filter_by(meeting_id=meeting_id).first()
            self.assertIsNotNone(record)
            self.assertEqual(record.board_recommendation, "Board recommends a bounded seizure-detection pilot with one hospital partner.")
            self.assertEqual(record.rationale, "The pilot tests demand and feasibility before a larger commitment.")
            self.assertEqual(record.founder_decision, "approved")
            self.assertEqual(record.actual_outcome, "")
            self.assertEqual(record.lifecycle.value, "open")
        finally:
            db.close()

    def test_decision_record_crud_and_spec_fields(self):
        review_date = (date.today() + timedelta(days=90)).isoformat()
        create = self.client.post(
            "/api/decisions",
            json={
                "decision": "Run a bounded seizure-detection pilot",
                "rationale": "Test demand before committing capital.",
                "board_recommendation": "Approve bounded pilot.",
                "founder_decision": "approved",
                "conditions": [
                    {"label": "Dataset access obtained", "status": "pending"},
                    {"label": "Clinical advisor engaged", "status": "met"},
                ],
                "owner": "CEO",
                "target_date": review_date,
                "success_criteria": "5 pilot hospitals committed; 120 patients monitored.",
                "review_date": review_date,
            },
        )
        self.assertEqual(create.status_code, 201)
        body = create.json()
        self.assertEqual(body["owner"], "CEO")
        self.assertEqual(len(body["conditions"]), 2)
        self.assertTrue(all(condition["id"] for condition in body["conditions"]))
        decision_id = body["id"]

        fetched = self.client.get(f"/api/decisions/{decision_id}")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["success_criteria"], "5 pilot hospitals committed; 120 patients monitored.")

        updated = self.client.patch(
            f"/api/decisions/{decision_id}",
            json={"owner": "CTO", "success_criteria": "3 pilot hospitals committed."},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["owner"], "CTO")
        self.assertEqual(updated.json()["success_criteria"], "3 pilot hospitals committed.")

    def test_review_due_when_review_date_passed_and_cleared_by_review(self):
        past = (date.today() - timedelta(days=7)).isoformat()
        create = self.client.post(
            "/api/decisions",
            json={
                "decision": "Defer commercial launch until regulatory pathway is clearer",
                "review_date": past,
                "success_criteria": "Regulatory opinion received.",
            },
        )
        self.assertEqual(create.status_code, 201)
        decision_id = create.json()["id"]

        due = self.client.get("/api/decisions/due")
        self.assertEqual(due.status_code, 200)
        self.assertIn(decision_id, [item["id"] for item in due.json()])

        reviewed = self.client.post(
            f"/api/decisions/{decision_id}/review",
            json={
                "outcome": "Regulatory pathway turned out to be viable earlier than expected.",
                "notes": "Reassess launch timeline in Q1 planning.",
                "lifecycle": "closed",
            },
        )
        self.assertEqual(reviewed.status_code, 200)
        body = reviewed.json()
        self.assertEqual(body["actual_outcome"], "Regulatory pathway turned out to be viable earlier than expected.")
        self.assertEqual(body["lifecycle"], "closed")
        self.assertIn("Reassess launch timeline in Q1 planning.", body["review_notes"])

        due_after = self.client.get("/api/decisions/due")
        self.assertNotIn(decision_id, [item["id"] for item in due_after.json()])

    def test_condition_changed_to_met_makes_review_due_until_reviewed(self):
        future = (date.today() + timedelta(days=60)).isoformat()
        create = self.client.post(
            "/api/decisions",
            json={
                "decision": "Proceed with customer discovery for seizure detection",
                "review_date": future,
                "conditions": [{"label": "Customer interviews completed", "status": "pending"}],
            },
        )
        self.assertEqual(create.status_code, 201)
        decision_id = create.json()["id"]

        due_now = self.client.get("/api/decisions/due")
        self.assertNotIn(decision_id, [item["id"] for item in due_now.json()])

        condition = create.json()["conditions"][0]
        patched = self.client.patch(
            f"/api/decisions/{decision_id}",
            json={"conditions": [{**condition, "status": "met"}]},
        )
        self.assertEqual(patched.status_code, 200)
        self.assertEqual(patched.json()["conditions"][0]["status"], "met")

        due_after_change = self.client.get("/api/decisions/due")
        self.assertIn(decision_id, [item["id"] for item in due_after_change.json()])

        self.client.post(
            f"/api/decisions/{decision_id}/review",
            json={"outcome": "Interview loop finished; demand confirmed.", "notes": "Assumption validated."},
        )
        due_final = self.client.get("/api/decisions/due")
        self.assertNotIn(decision_id, [item["id"] for item in due_final.json()])

    def test_memory_recall_ranks_relevant_decisions_and_excludes_unrelated(self):
        for decision in (
            "Seizure detection pilot approved for two hospital partners",
            "Seizure prediction research roadmap scoped to epilepsy units",
            "Pricing strategy for consumable EEG electrode refills",
        ):
            response = self.client.post(
                "/api/decisions",
                json={"decision": decision, "founder_decision": "approved"},
            )
            self.assertEqual(response.status_code, 201)

        memory = self.client.get("/api/decisions/memory", params={"q": "seizure detection"})
        self.assertEqual(memory.status_code, 200)
        body = memory.json()
        self.assertGreaterEqual(body["total_matches"], 2)
        decisions = [record["decision"] for record in body["records"]]
        self.assertIn("Seizure detection pilot approved for two hospital partners", decisions)
        self.assertNotIn("Pricing strategy for consumable EEG electrode refills", decisions)
        self.assertIn("seizure detection", body["context_block"].lower().replace("\n", " "))

    def test_memory_recall_respects_limit_and_meeting_exclusion(self):
        meeting_id = self._create_meeting_with_resolution(title="Second seizure detection conclave")
        for index in range(4):
            self.client.post(
                "/api/decisions",
                json={
                    "meeting_id": meeting_id if index == 0 else None,
                    "decision": f"Seizure detection feasibility condition {index}",
                },
            )
        limited = self.client.get("/api/decisions/memory", params={"q": "seizure detection", "limit": 2})
        self.assertEqual(len(limited.json()["records"]), 2)

        excluded = self.client.get(
            "/api/decisions/memory",
            params={"q": "seizure detection", "exclude_meeting_id": meeting_id, "limit": 10},
        )
        self.assertNotIn(meeting_id, [record["meeting_id"] for record in excluded.json()["records"]])

    def test_sync_backfills_decisions_from_existing_resolutions(self):
        self._create_meeting_with_resolution()
        synced = self.client.post("/api/decisions/sync")
        self.assertEqual(synced.status_code, 200)
        self.assertEqual(synced.json()["created"], 1)

        synced_again = self.client.post("/api/decisions/sync")
        self.assertEqual(synced_again.json()["created"], 0)
        self.assertEqual(synced_again.json()["updated"], 1)

    def test_progress_exposes_institutional_memory_snapshot(self):
        meeting_id = self._create_meeting_with_resolution()
        memory_payload = [
            {
                "id": 42,
                "meeting_id": 7,
                "meeting_title": "Seizure detection conclave",
                "decision": "Seizure detection pilot approved for two hospital partners",
                "rationale": "Demand unproven.",
                "board_recommendation": "Approve pilot.",
                "founder_decision": "approved",
                "founder_notes": "",
                "conditions": [{"id": "abc123", "label": "Dataset access obtained", "status": "pending", "note": "", "updated_at": None}],
                "owner": "CEO",
                "target_date": None,
                "success_criteria": "5 hospitals committed.",
                "review_date": "2030-01-01",
                "actual_outcome": "",
                "lifecycle": "open",
                "last_reviewed_at": None,
                "review_notes": "",
                "is_review_due": False,
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
            }
        ]
        db = self.session_factory()
        try:
            db.add(MeetingRunCheckpoint(
                meeting_id=meeting_id,
                phase="institutional_memory",
                role="BOARD",
                content=json.dumps(memory_payload),
                model_provider="system",
                model_name="institutional-memory-snapshot-v1",
            ))
            db.commit()
        finally:
            db.close()

        progress = self.client.get(f"/api/meetings/{meeting_id}/progress")
        self.assertEqual(progress.status_code, 200)
        body = progress.json()
        self.assertEqual(body["institutional_memory"][0]["decision"], memory_payload[0]["decision"])
        self.assertNotIn("institutional_memory", [checkpoint["phase"] for checkpoint in body["checkpoints"]])

    def test_is_review_due_respects_lifecycle(self):
        past = date.today() - timedelta(days=1)
        record = DecisionRecord(
            decision="Closed decision",
            review_date=past,
            lifecycle=DecisionLifecycle.closed,
        )
        self.assertFalse(is_review_due(record))
        record.lifecycle = DecisionLifecycle.open
        self.assertTrue(is_review_due(record))


if __name__ == "__main__":
    unittest.main()
