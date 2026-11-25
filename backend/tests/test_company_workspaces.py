import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agents.graph import build_synthesis_input
from app.auth import get_current_user
from app.company import company_context_dict, ensure_company, format_company_context
from app.database import Base, get_db
from app.models import (
    AgentContribution,
    ApprovalEvent,
    BoardMeeting,
    DecisionLifecycle,
    DecisionRecord,
    DecisionStatus,
    EvidenceRecord,
    MeetingRunCheckpoint,
    MeetingStatus,
)
from app.routers import companies, decisions, performance
from app.routers import meetings as meeting_routes


class CompanyWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "company.db"
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
        app.include_router(companies.router)
        app.include_router(decisions.router)
        app.include_router(performance.router)
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

    def _meeting(self, title="Seizure detection conclave", status=MeetingStatus.completed):
        db = self.session_factory()
        try:
            meeting = BoardMeeting(
                company_id=self.company_id,
                title=title,
                agenda="Should we commit to a seizure detection pilot?",
                founder_context="Dataset access is pending.",
                status=status,
            )
            db.add(meeting)
            db.commit()
            db.refresh(meeting)
            return meeting.id
        finally:
            db.close()

    def _decision(self, **overrides):
        payload = {
            "decision": "Run a bounded seizure-detection pilot",
            "rationale": "Prove demand before committing capital.",
            "founder_decision": "approved",
            "lifecycle": DecisionLifecycle.open,
            **overrides,
        }
        db = self.session_factory()
        try:
            record = DecisionRecord(company_id=self.company_id, **payload)
            db.add(record)
            db.commit()
            db.refresh(record)
            return record.id
        finally:
            db.close()

    def _evidence(self, claim="Detection latency of 12 seconds in the pilot cohort"):
        db = self.session_factory()
        try:
            record = EvidenceRecord(
                company_id=self.company_id,
                claim=claim,
                category="scientific",
                classification="assumption",
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            return record.id
        finally:
            db.close()

    def test_company_defaults_are_seeded_and_owner_configurable(self):
        response = self.client.get("/api/company")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["name"], "Neurotechnology Venture")
        self.assertEqual(body["owner"], "Founder")
        self.assertEqual(body["stage"], "seed")
        self.assertTrue(body["strategic_priorities"])

        updated = self.client.patch(
            "/api/company",
            json={
                "owner": "Chris",
                "stage": "pre-seed",
                "mission": "Bring seizure detection to every epilepsy unit.",
            },
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["owner"], "Chris")
        self.assertEqual(updated.json()["stage"], "pre-seed")
        self.assertEqual(
            updated.json()["mission"],
            "Bring seizure detection to every epilepsy unit.",
        )

    def test_priority_constraint_and_assumption_crud(self):
        priority = self.client.post(
            "/api/company/priorities",
            json={
                "title": "Sign two pilot hospitals",
                "description": "Close signed LOIs before building the next feature.",
                "status": "active",
                "target_date": (date.today() + timedelta(days=60)).isoformat(),
            },
        )
        self.assertEqual(priority.status_code, 201)
        self.assertTrue(priority.json()["id"])

        patched = self.client.patch(
            f"/api/company/priorities/{priority.json()['id']}",
            json={"status": "achieved"},
        )
        self.assertEqual(patched.status_code, 200)
        self.assertEqual(patched.json()["status"], "achieved")

        constraint = self.client.post(
            "/api/company/constraints",
            json={
                "label": "No PHI outside partners",
                "description": "Patient data stays in approved environments.",
                "severity": "high",
            },
        )
        self.assertEqual(constraint.status_code, 201)

        assumption = self.client.post(
            "/api/company/financial-assumptions",
            json={"label": "Runway", "value": "9", "unit": "months"},
        )
        self.assertEqual(assumption.status_code, 201)

        company = self.client.get("/api/company").json()
        titles = [item["title"] for item in company["strategic_priorities"]]
        self.assertIn("Sign two pilot hospitals", titles)
        self.assertTrue(
            any(item["label"] == "No PHI outside partners" for item in company["constraints"])
        )
        self.assertTrue(
            any(item["label"] == "Runway" for item in company["financial_assumptions"])
        )

        deleted = self.client.delete(
            f"/api/company/priorities/{priority.json()['id']}"
        )
        self.assertEqual(deleted.status_code, 204)
        remaining = [
            item["title"]
            for item in self.client.get("/api/company").json()["strategic_priorities"]
        ]
        self.assertNotIn("Sign two pilot hospitals", remaining)

    def test_knowledge_approval_links_evidence(self):
        evidence_id = self._evidence()
        created = self.client.post(
            "/api/company/knowledge",
            json={
                "title": "Pilot latency result",
                "summary": "Median detection latency was 12 seconds in the pilot cohort.",
                "category": "scientific",
                "source_reference": "Pilot dataset v1",
                "evidence_id": evidence_id,
            },
        )
        self.assertEqual(created.status_code, 201)
        body = created.json()
        self.assertEqual(body["evidence_id"], evidence_id)
        self.assertTrue(body["approved_at"])

        missing = self.client.post(
            "/api/company/knowledge",
            json={"title": "Unknown link", "evidence_id": 9999},
        )
        self.assertEqual(missing.status_code, 404)

        company = self.client.get("/api/company").json()
        self.assertEqual(len(company["approved_knowledge"]), 1)
        self.assertEqual(
            company["approved_knowledge"][0]["title"], "Pilot latency result"
        )

        removed = self.client.delete(f"/api/company/knowledge/{body['id']}")
        self.assertEqual(removed.status_code, 204)

    def test_company_context_aggregates_and_risks(self):
        self._meeting()
        self._decision(
            review_date=date.today() - timedelta(days=5),
            conditions=[
                {
                    "id": "abc123",
                    "label": "Dataset access obtained",
                    "status": "breached",
                    "note": "Partner withdrew.",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            ],
        )
        self.client.post(
            "/api/company/constraints",
            json={"label": "Runway cap", "severity": "high"},
        )

        context = self.client.get("/api/company/context")
        self.assertEqual(context.status_code, 200)
        body = context.json()
        self.assertGreaterEqual(body["counts"]["meetings_total"], 1)
        self.assertEqual(body["counts"]["decisions_total"], 1)
        self.assertEqual(body["counts"]["decisions_due"], 1)
        kinds = {risk["kind"] for risk in body["risks"]}
        self.assertIn("decision_condition_breached", kinds)
        self.assertIn("constraint", kinds)
        self.assertEqual(body["risks"][0]["severity"], "high")
        self.assertEqual(body["recent_decisions"][0]["id"], 1)
        self.assertIn("mission", body["company"])

    def test_company_context_is_injected_into_prompts(self):
        db = self.session_factory()
        try:
            company = ensure_company(db)
            context = company_context_dict(company)
        finally:
            db.close()

        block = format_company_context(context)
        self.assertIn("COMPANY CONTEXT", block)
        self.assertIn("MISSION:", block)
        self.assertIn("STRATEGIC PRIORITIES:", block)
        self.assertIn("CONSTRAINTS:", block)

        state = {
            "title": "Seizure detection next steps",
            "agenda": "Keep prioritising detection?",
            "founder_context": "",
            "assessments": {},
            "critiques": {},
            "revisions": {},
            "evidence_register": [],
            "company_context": context,
        }
        prompt = build_synthesis_input(state, 8000)
        self.assertIn("COMPANY CONTEXT", prompt)
        self.assertIn("STRATEGIC PRIORITIES", prompt)

        without = build_synthesis_input(
            {**state, "company_context": {}}, 8000
        )
        self.assertNotIn("COMPANY CONTEXT", without)

    def test_performance_aggregates_executives_and_outcomes(self):
        meeting_id = self._meeting()
        db = self.session_factory()
        try:
            db.add_all(
                [
                    AgentContribution(
                        meeting_id=meeting_id,
                        role="CEO",
                        phase="assessment",
                        assessment="CEO assessment body",
                        critique="CEO challenge body",
                        model_provider="local",
                        model_name="qwen",
                    ),
                    AgentContribution(
                        meeting_id=meeting_id,
                        role="CFO",
                        phase="assessment",
                        assessment="CFO assessment body",
                        model_provider="openai",
                        model_name="gpt-4.1-mini",
                    ),
                    MeetingRunCheckpoint(
                        meeting_id=meeting_id,
                        phase="revision",
                        role="CEO",
                        content="CEO revision body",
                    ),
                ]
            )
            db.add(
                DecisionRecord(
                    company_id=self.company_id,
                    meeting_id=meeting_id,
                    decision="Pilot approved",
                    founder_decision="approved",
                    actual_outcome="Two hospitals signed.",
                    lifecycle=DecisionLifecycle.closed,
                )
            )
            db.add(
                DecisionRecord(
                    company_id=self.company_id,
                    decision="Hire a clinical lead",
                    founder_decision="deferred",
                    lifecycle=DecisionLifecycle.open,
                    review_date=date.today() - timedelta(days=1),
                )
            )
            db.commit()
        finally:
            db.close()

        response = self.client.get("/api/performance")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["approved"], 1)
        self.assertEqual(body["deferred"], 1)
        self.assertEqual(body["decisions_with_outcome"], 1)
        self.assertGreaterEqual(body["due_decisions"], 1)
        roles = {item["role"]: item for item in body["executives"]}
        self.assertEqual(roles["CEO"]["assessments"], 1)
        self.assertEqual(roles["CEO"]["challenges"], 1)
        self.assertEqual(roles["CEO"]["revisions"], 1)
        self.assertEqual(roles["CFO"]["assessments"], 1)
        self.assertEqual(roles["CFO"]["models"], ["openai:gpt-4.1-mini"])
        self.assertTrue(body["recent_outcomes"])

    def test_progress_exposes_company_context_snapshot(self):
        meeting_id = self._meeting(status=MeetingStatus.completed)
        db = self.session_factory()
        try:
            company = ensure_company(db)
            snapshot = company_context_dict(company)
            db.add(
                MeetingRunCheckpoint(
                    meeting_id=meeting_id,
                    phase="company_context",
                    role="BOARD",
                    content=json.dumps(snapshot),
                    model_provider="system",
                    model_name="company-context-snapshot-v1",
                )
            )
            db.commit()
        finally:
            db.close()

        progress = self.client.get(f"/api/meetings/{meeting_id}/progress")
        self.assertEqual(progress.status_code, 200)
        body = progress.json()
        self.assertEqual(body["company_context"]["name"], "Neurotechnology Venture")
        self.assertNotIn(
            "company_context",
            [checkpoint["phase"] for checkpoint in body["checkpoints"]],
        )

    def test_governance_lists_approval_events(self):
        meeting_id = self._meeting()
        db = self.session_factory()
        try:
            db.add(
                ApprovalEvent(
                    meeting_id=meeting_id,
                    action="approve",
                    actor="Founder",
                    comments="Proceed with the pilot.",
                )
            )
            db.commit()
        finally:
            db.close()

        response = self.client.get("/api/company/governance")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["events"][0]["action"], "approve")
        self.assertEqual(body["events"][0]["meeting_id"], meeting_id)
        self.assertEqual(body["counts"]["approve"], 1)
        self.assertEqual(body["policy"]["decision_authority"], "Founder")


if __name__ == "__main__":
    unittest.main()
