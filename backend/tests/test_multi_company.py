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
from app.routers import companies, companies_admin, decisions, evidence, meetings, operations, performance


class MultiCompanyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "multi-company.db"
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        _seed = self.session_factory()
        self.default_company_id = ensure_company(_seed).id
        _seed.close()

        app = FastAPI()
        app.include_router(companies.router)
        app.include_router(companies_admin.router)
        app.include_router(meetings.router)
        app.include_router(decisions.router)
        app.include_router(evidence.evidence_router)
        app.include_router(performance.router)
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

    @staticmethod
    def _headers(company_id):
        return {"X-Company-Id": str(company_id)}

    def _create_company(self, name="Northstar Labs", **overrides):
        response = self.client.post(
            "/api/companies",
            json={
                "name": name,
                "mission": "Build a second venture.",
                "stage": "pre-seed",
                **overrides,
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def _create_meeting(self, company_id, title):
        response = self.client.post(
            "/api/meetings",
            headers=self._headers(company_id),
            json={"title": title, "agenda": "Decide the next milestone.", "founder_context": ""},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _create_evidence(self, company_id, claim):
        response = self.client.post(
            "/api/evidence",
            headers=self._headers(company_id),
            json={
                "claim": claim,
                "category": "scientific",
                "classification": "assumption",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_companies_have_independent_profiles_and_switching_selects_them(self):
        default = self.client.get("/api/companies").json()
        self.assertEqual(len(default), 1)
        self.assertEqual(default[0]["id"], self.default_company_id)

        second = self._create_company()
        self.assertNotEqual(second["id"], self.default_company_id)

        updated = self.client.patch(
            f"/api/companies/{second['id']}",
            json={"mission": "A distinct mission for the second company."},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(
            updated.json()["mission"], "A distinct mission for the second company."
        )

        switched = self.client.get(
            "/api/company", headers=self._headers(second["id"])
        )
        self.assertEqual(switched.status_code, 200)
        self.assertEqual(switched.json()["name"], "Northstar Labs")
        self.assertEqual(
            switched.json()["mission"], "A distinct mission for the second company."
        )

        original = self.client.get(
            "/api/company", headers=self._headers(self.default_company_id)
        )
        self.assertEqual(original.json()["name"], "Neurotechnology Venture")
        self.assertNotEqual(
            original.json()["mission"], "A distinct mission for the second company."
        )

        listed = self.client.get("/api/companies").json()
        self.assertEqual(len(listed), 2)
        self.assertEqual(
            {item["name"] for item in listed},
            {"Neurotechnology Venture", "Northstar Labs"},
        )

    def test_switch_header_isolates_conclaves_evidence_decisions_and_artifacts(self):
        second = self._create_company()
        first_meeting = self._create_meeting(
            self.default_company_id, "First company conclave"
        )
        second_meeting = self._create_meeting(second["id"], "Second company conclave")
        self._create_evidence(self.default_company_id, "First company claim")
        self._create_evidence(second["id"], "Second company claim")

        first_meetings = self.client.get(
            "/api/meetings", headers=self._headers(self.default_company_id)
        ).json()
        second_meetings = self.client.get(
            "/api/meetings", headers=self._headers(second["id"])
        ).json()
        self.assertEqual([item["id"] for item in first_meetings], [first_meeting["id"]])
        self.assertEqual([item["id"] for item in second_meetings], [second_meeting["id"]])

        first_evidence = self.client.get(
            "/api/evidence", headers=self._headers(self.default_company_id)
        ).json()
        second_evidence = self.client.get(
            "/api/evidence", headers=self._headers(second["id"])
        ).json()
        self.assertEqual(
            [item["claim"] for item in first_evidence], ["First company claim"]
        )
        self.assertEqual(
            [item["claim"] for item in second_evidence], ["Second company claim"]
        )

        decision = self.client.post(
            "/api/decisions",
            headers=self._headers(second["id"]),
            json={"decision": "Second company decree", "lifecycle": "open"},
        )
        self.assertEqual(decision.status_code, 201, decision.text)
        self.assertEqual(
            self.client.get(
                "/api/decisions", headers=self._headers(self.default_company_id)
            ).json(),
            [],
        )
        self.assertEqual(
            [
                item["decision"]
                for item in self.client.get(
                    "/api/decisions", headers=self._headers(second["id"])
                ).json()
            ],
            ["Second company decree"],
        )

        artifact = self.client.post(
            "/api/operations/artifacts",
            headers=self._headers(second["id"]),
            json={"kind": "company_review", "title": "Second company review"},
        )
        self.assertEqual(artifact.status_code, 201, artifact.text)
        self.assertEqual(
            self.client.get(
                "/api/operations/artifacts",
                headers=self._headers(self.default_company_id),
            ).json(),
            [],
        )
        self.assertEqual(
            len(
                self.client.get(
                    "/api/operations/artifacts", headers=self._headers(second["id"])
                ).json()
            ),
            1,
        )

        scorecard_second = self.client.get(
            "/api/performance", headers=self._headers(second["id"])
        ).json()
        self.assertEqual(scorecard_second["meetings_total"], 1)

        # Cross-company access is refused, not silently scoped.
        cross = self.client.get(
            f"/api/meetings/{second_meeting['id']}",
            headers=self._headers(self.default_company_id),
        )
        self.assertEqual(cross.status_code, 404)
        cross_artifact = self.client.get(
            f"/api/operations/artifacts/{artifact.json()['id']}",
            headers=self._headers(self.default_company_id),
        )
        self.assertEqual(cross_artifact.status_code, 404)

    def test_company_deletion_guards_the_last_and_non_empty_company(self):
        second = self._create_company()
        self._create_meeting(second["id"], "Work in progress")

        blocked = self.client.delete(f"/api/companies/{second['id']}")
        self.assertEqual(blocked.status_code, 409)

        forced = self.client.delete(f"/api/companies/{second['id']}?force=true")
        self.assertEqual(forced.status_code, 204)
        self.assertEqual(
            [item["id"] for item in self.client.get("/api/companies").json()],
            [self.default_company_id],
        )

        last = self.client.delete(f"/api/companies/{self.default_company_id}?force=true")
        self.assertEqual(last.status_code, 409)

    def test_unknown_company_header_is_rejected(self):
        response = self.client.get("/api/company", headers=self._headers(99999))
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
