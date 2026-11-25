import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import get_current_user
from app.company import ensure_company
from app.database import Base, get_db
from app.models import BoardMeeting, DecisionLifecycle, DecisionRecord
from app.routers import operations


class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "operations.db"
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
        app.include_router(operations.router)
        app.dependency_overrides[get_current_user] = lambda: {
            "sub": "founder",
            "email": "founder@example.com",
        }
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

    def _create(self, kind="project_plan", **overrides):
        payload = {
            "kind": kind,
            "title": f"{kind.replace('_', ' ').title()} draft",
            "brief": "Bound the next milestone and its evidence gates.",
            **overrides,
        }
        return self.client.post("/api/operations/artifacts", json=payload)

    def test_capabilities_are_internal_and_require_approval(self):
        response = self.client.get("/api/operations/capabilities")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        kinds = {item["kind"] for item in body["capabilities"]}
        self.assertEqual(
            kinds,
            {
                "project_plan",
                "financial_model",
                "investor_document",
                "task_list",
                "architecture_document",
                "milestone_review",
                "company_review",
            },
        )
        self.assertTrue(all(item["approval_required"] for item in body["capabilities"]))
        self.assertTrue(all(not item["external"] for item in body["capabilities"]))
        self.assertTrue(all(item["enabled"] for item in body["capabilities"]))
        self.assertTrue(body["policy"]["approval_required"])
        self.assertFalse(body["policy"]["external_actions_enabled"])
        self.assertIn("no external action", body["policy"]["execution_scope"].lower())

    def test_create_generates_a_draft_from_company_context(self):
        response = self._create()
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["status"], "draft")
        self.assertEqual(body["kind"], "project_plan")
        self.assertIn("Objective", body["payload"]["markdown"])
        self.assertIn("internal draft", body["payload"]["disclaimer"])
        self.assertFalse(body["permissions"]["external"])
        self.assertTrue(body["permissions"]["approval_required"])
        self.assertEqual([event["action"] for event in body["events"]], ["generated"])
        self.assertIn("Neurotechnology Venture", body["payload"]["markdown"])

    def test_external_actions_are_refused(self):
        response = self._create(external_actions=True)
        self.assertEqual(response.status_code, 403)
        self.assertIn("External actions are disabled", response.json()["detail"])

    def test_draft_submit_approve_lifecycle_and_audit(self):
        created = self._create().json()
        submitted = self.client.post(
            f"/api/operations/artifacts/{created['id']}/submit"
        )
        self.assertEqual(submitted.status_code, 200)
        self.assertEqual(submitted.json()["status"], "pending_approval")

        approved = self.client.post(
            f"/api/operations/artifacts/{created['id']}/approve",
            json={"comments": "Approved for internal planning."},
        )
        self.assertEqual(approved.status_code, 200)
        body = approved.json()
        self.assertEqual(body["status"], "approved")
        self.assertEqual(body["approved_by"], "founder@example.com")
        self.assertIsNotNone(body["approved_at"])
        self.assertEqual(
            [event["action"] for event in body["events"]],
            ["generated", "submitted", "approved"],
        )

        regenerate = self.client.post(
            f"/api/operations/artifacts/{created['id']}/regenerate"
        )
        self.assertEqual(regenerate.status_code, 409)

    def test_rejected_artifact_can_be_regenerated(self):
        created = self._create().json()
        self.client.post(f"/api/operations/artifacts/{created['id']}/submit")
        rejected = self.client.post(
            f"/api/operations/artifacts/{created['id']}/reject",
            json={"comments": "Tighten the evidence gate."},
        )
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(rejected.json()["status"], "rejected")
        self.assertEqual(rejected.json()["rejection_reason"], "Tighten the evidence gate.")

        regenerated = self.client.post(
            f"/api/operations/artifacts/{created['id']}/regenerate"
        )
        self.assertEqual(regenerated.status_code, 200)
        self.assertEqual(regenerated.json()["status"], "draft")
        self.assertEqual(regenerated.json()["rejection_reason"], "")

    def test_every_capability_generates_a_substantive_draft(self):
        for kind in (
            "project_plan",
            "financial_model",
            "investor_document",
            "task_list",
            "architecture_document",
            "milestone_review",
            "company_review",
        ):
            with self.subTest(kind=kind):
                response = self._create(kind=kind)
                self.assertEqual(response.status_code, 201)
                payload = response.json()["payload"]
                self.assertGreater(len(payload["markdown"]), 150)
                self.assertEqual(payload["kind"], kind)

    def test_financial_model_uses_recorded_assumptions(self):
        response = self._create(kind="financial_model")
        self.assertEqual(response.status_code, 201)
        markdown = response.json()["payload"]["markdown"]
        self.assertIn("Pilot budget", markdown)
        self.assertIn("Monthly burn", markdown)
        self.assertIn("Runway", markdown)
        self.assertIn("Scenario", markdown)

    def test_artifact_can_link_to_a_decision_and_meeting(self):
        db = self.session_factory()
        try:
            meeting = BoardMeeting(
                company_id=self.company_id,
                title="Pilot conclave",
                agenda="Approve the pilot?",
                founder_context="",
            )
            db.add(meeting)
            db.commit()
            db.refresh(meeting)
            decision = DecisionRecord(
                company_id=self.company_id,
                decision="Approve the pilot",
                founder_decision="approved",
                lifecycle=DecisionLifecycle.open,
            )
            db.add(decision)
            db.commit()
            db.refresh(decision)
            meeting_id, decision_id = meeting.id, decision.id
        finally:
            db.close()

        response = self._create(meeting_id=meeting_id, decision_id=decision_id)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["meeting_id"], meeting_id)
        self.assertEqual(response.json()["decision_id"], decision_id)

        missing = self._create(meeting_id=9999)
        self.assertEqual(missing.status_code, 404)


if __name__ == "__main__":
    unittest.main()
