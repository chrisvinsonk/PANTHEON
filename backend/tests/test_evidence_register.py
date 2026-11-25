import asyncio
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import get_current_user
from app.agents.contracts import CLAIM_CATEGORIES, build_position_extraction
from app.agents.graph import format_evidence_register
from app.config import Settings
from app.company import ensure_company
from app.database import Base, get_db
from app.llm_config import decrypt_api_key
from app.models import (
    BoardMeeting,
    EvidenceRecord,
    MeetingRunCheckpoint,
    ResearchProviderConfig,
)
from app.routers import evidence, meetings as meeting_routes
from app.routers.meetings import _apply_evidence_outcomes
from app.schemas import ResearchSourceOut


class EvidenceRegisterTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "evidence.db"
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        _seed = self.session_factory()
        self.company_id = ensure_company(_seed).id
        _seed.close()
        self.encryption_key = Fernet.generate_key().decode("ascii")
        self.settings = Settings(llm_config_encryption_key=self.encryption_key)
        self.settings_patch = patch("app.llm_config.get_settings", return_value=self.settings)
        self.settings_patch.start()

        app = FastAPI()
        app.include_router(evidence.evidence_router)
        app.include_router(evidence.research_router)
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
        self.settings_patch.stop()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def _create_draft_meeting(self):
        db = self.session_factory()
        try:
            meeting = BoardMeeting(
                company_id=self.company_id,
                title="Evidence test conclave",
                agenda="Check evidence ingestion and provenance.",
            )
            db.add(meeting)
            db.commit()
            db.refresh(meeting)
            return meeting.id
        finally:
            db.close()

    def test_verified_claim_needs_source_and_verification_note(self):
        response = self.client.post(
            "/api/evidence",
            json={
                "claim": "This dataset contains 120 patients.",
                "category": "scientific",
                "classification": "verified",
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("verification note", str(response.json()["detail"]))

        response = self.client.post(
            "/api/evidence",
            json={
                "claim": "This dataset contains 120 patients.",
                "category": "scientific",
                "classification": "verified",
                "source_url": "https://example.org/dataset",
                "verification_note": "Count checked against the dataset documentation.",
            },
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["classification"], "verified")

    def test_claim_persists_source_provenance_and_draft_meeting_link(self):
        meeting_id = self._create_draft_meeting()
        response = self.client.post(
            "/api/evidence",
            json={
                "claim": "A device received a specific FDA 510(k) decision.",
                "category": "regulatory",
                "classification": "unknown",
                "source_provider": "openfda",
                "source_title": "FDA 510(k) entry",
                "source_reference": "FDA 510(k): K123456",
                "source_url": "https://www.accessdata.fda.gov/device/K123456",
                "publication_date": "2025-01-02",
                "evidence_quality": "unassessed",
                "limitations": "The record does not establish another product's pathway.",
                "source_excerpt": "Search-result excerpt only.",
                "meeting_ids": [meeting_id],
            },
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["meeting_ids"], [meeting_id])
        self.assertEqual(body["source_provider"], "openfda")
        self.assertEqual(body["source_reference"], "FDA 510(k): K123456")
        self.assertIsNotNone(body["retrieved_at"])

        listed = self.client.get(f"/api/evidence?meeting_id={meeting_id}")
        self.assertEqual(len(listed.json()), 1)
        self.assertEqual(listed.json()[0]["claim"], body["claim"])

    def test_new_meeting_can_attach_evidence_before_its_run(self):
        record_response = self.client.post(
            "/api/evidence",
            json={
                "claim": "A customer interview is needed to validate willingness to pay.",
                "category": "commercial",
                "classification": "hypothesis",
            },
        )
        self.assertEqual(record_response.status_code, 201)
        evidence_id = record_response.json()["id"]

        meeting_response = self.client.post(
            "/api/meetings",
            json={
                "title": "Evidence-linked conclave",
                "agenda": "Evaluate the market hypothesis and next validation step.",
                "evidence_ids": [evidence_id],
            },
        )
        self.assertEqual(meeting_response.status_code, 200)
        meeting_id = meeting_response.json()["id"]
        record = self.client.get("/api/evidence").json()[0]
        self.assertEqual(record["meeting_ids"], [meeting_id])

    def test_clinical_trials_result_uses_registry_first_posted_date(self):
        client = AsyncMock()
        client.get = AsyncMock(return_value=httpx.Response(
            200,
            json={
                "studies": [{
                    "protocolSection": {
                        "identificationModule": {
                            "nctId": "NCT01234567",
                            "briefTitle": "Home monitoring feasibility study",
                        },
                        "statusModule": {
                            "studyFirstPostDateStruct": {"date": "2024-06-17"},
                            "overallStatus": "COMPLETED",
                        },
                    },
                }],
            },
            request=httpx.Request("GET", "https://clinicaltrials.gov/api/v2/studies"),
        ))

        results = asyncio.run(evidence._search_clinical_trials(
            client,
            "home monitoring",
            5,
            datetime.now(timezone.utc),
        ))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].publication_date.isoformat(), "2024-06-17")
        self.assertEqual(results[0].source_reference, "NCT01234567")

    def test_evidence_prompt_stays_bounded_and_keeps_each_attached_id(self):
        records = [
            {
                "id": index,
                "claim": f"Claim {index}. " + ("claim detail " * 500),
                "category": "scientific",
                "classification": "hypothesis",
                "source_provider": "pubmed",
                "evidence_quality": "unassessed",
                "source_title": "Study " + ("title " * 100),
                "source_reference": "PMID:12345",
                "source_url": "https://example.org/study",
                "publication_date": "2025-01-01",
                "retrieved_at": "2025-01-02T00:00:00Z",
                "relying_executives": [],
                "challenged": False,
                "disputed": False,
                "limitations": "Limitation " * 500,
                "source_excerpt": "Unverified excerpt " * 500,
            }
            for index in range(1, 13)
        ]

        context = format_evidence_register(records)

        self.assertLessEqual(len(context), 6000)
        for evidence_id in range(1, 13):
            self.assertIn(f"EVIDENCE-{evidence_id} ", context)
        self.assertNotIn("Unverified excerpt", context)

    def test_tavily_secret_is_encrypted_and_never_returned(self):
        secret = "tavily-test-secret"
        response = self.client.put(
            "/api/research/settings/tavily",
            json={"api_key": secret},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["web_search_configured"])
        self.assertNotIn(secret, response.text)

        db = self.session_factory()
        try:
            config = db.query(ResearchProviderConfig).one()
            self.assertNotEqual(config.encrypted_api_key, secret)
            self.assertEqual(decrypt_api_key(config.encrypted_api_key), secret)
        finally:
            db.close()

    def test_research_results_are_labeled_as_leads_not_verified_claims(self):
        now = datetime.now(timezone.utc)
        result = ResearchSourceOut(
            provider="pubmed",
            title="A seizure-monitoring study",
            url="https://pubmed.ncbi.nlm.nih.gov/123456/",
            source_reference="PMID:123456",
            retrieved_at=now,
            excerpt="Search metadata only.",
            limitations=evidence.EVIDENCE_LIMITATIONS,
        )
        search_patch = patch(
            "app.routers.evidence._search_pubmed",
            new=AsyncMock(return_value=[result]),
        )
        with search_patch:
            response = self.client.post(
                "/api/research/search",
                json={"query": "seizure monitoring", "providers": ["pubmed"]},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["results"][0]["source_reference"], "PMID:123456")
        self.assertIn("not proof", body["results"][0]["limitations"])
        self.assertNotIn("classification", body["results"][0])

    def test_assessment_reliance_and_challenge_dispute_update_persisted_register(self):
        db = self.session_factory()
        try:
            meeting = BoardMeeting(
                company_id=self.company_id,
                title="Evidence outcome test",
                agenda="Check evidence usage metadata.",
            )
            record = EvidenceRecord(
                company_id=self.company_id,
                claim="A candidate study supports a narrow feasibility hypothesis.",
                category="scientific",
                classification="hypothesis",
                source_title="Study record",
                source_reference="PMID:99",
                source_url="https://pubmed.ncbi.nlm.nih.gov/99/",
                evidence_quality="unassessed",
                limitations="Population applicability remains unresolved.",
            )
            db.add_all([meeting, record])
            db.commit()
            db.refresh(meeting)
            db.refresh(record)
            evidence_id = record.id
            snapshot = [{
                "id": evidence_id,
                "claim": record.claim,
                "category": record.category,
                "classification": record.classification,
                "source_title": record.source_title,
                "source_reference": record.source_reference,
                "source_url": record.source_url,
                "publication_date": None,
                "retrieved_at": None,
                "evidence_quality": record.evidence_quality,
                "limitations": record.limitations,
                "source_excerpt": "",
                "relying_executives": [],
                "challenged": False,
                "challenged_by": [],
                "disputed": False,
                "disputed_by": [],
                "dispute_notes": "",
            }]
            record.claim = "Edited after the meeting snapshot was captured."
            record.source_reference = "Updated reference"
            db.add(MeetingRunCheckpoint(
                meeting_id=meeting.id,
                phase="evidence_snapshot",
                role="BOARD",
                content=json.dumps(snapshot),
                model_provider="system",
                model_name="evidence-register-snapshot-v1",
            ))

            assessments = {}
            for role in ("CEO", "CFO", "CTO", "CSO"):
                assessment = {
                    "schema_version": 1,
                    "executive_position": "conditional",
                    "recommendation": f"{role} recommendation.",
                    "confidence": "medium",
                    **{field: [] for field in CLAIM_CATEGORIES},
                }
                if role == "CFO":
                    assessment["supporting_facts"] = [{
                        "claim": record.claim,
                        "classification": "hypothesis",
                        "source_evidence_ids": [evidence_id],
                    }]
                assessments[role] = json.dumps(assessment)
            extraction = build_position_extraction(assessments)
            critiques = {
                "CEO": json.dumps({
                    "schema_version": 1,
                    "challenges": [
                        {
                            "target_role": target,
                            "target_claim_id": (
                                f"{target}.supporting_facts.1"
                                if target == "CFO"
                                else f"{target}.recommendation"
                            ),
                            "challenge_question": "Does the evidence apply to this population?",
                            "why_it_matters": "The claim may not transfer to the intended users.",
                            "source_evidence_ids": [evidence_id] if target == "CFO" else [],
                            "disputed_evidence_ids": [evidence_id] if target == "CFO" else [],
                        }
                        for target in ("CFO", "CTO", "CSO")
                    ],
                })
            }

            _apply_evidence_outcomes(
                db,
                meeting.id,
                snapshot,
                {
                    "assessments": assessments,
                    "position_extraction": extraction.model_dump_json(),
                    "critiques": critiques,
                },
            )
            db.commit()
            db.refresh(record)

            self.assertEqual(record.relying_executives, ["CFO"])
            self.assertTrue(record.challenged)
            self.assertEqual(record.challenged_by, ["CEO"])
            self.assertTrue(record.disputed)
            self.assertEqual(record.disputed_by, ["CEO"])
            saved_snapshot = db.query(MeetingRunCheckpoint).filter_by(
                meeting_id=meeting.id,
                phase="evidence_snapshot",
            ).one()
            self.assertIn("disputed", json.loads(saved_snapshot.content)[0])
            self.assertEqual(
                json.loads(saved_snapshot.content)[0]["relying_executives"],
                ["CFO"],
            )
            self.assertEqual(
                json.loads(saved_snapshot.content)[0]["claim"],
                "A candidate study supports a narrow feasibility hypothesis.",
            )
            self.assertEqual(
                json.loads(saved_snapshot.content)[0]["source_reference"],
                "PMID:99",
            )
        finally:
            db.close()

