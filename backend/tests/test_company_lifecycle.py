"""Regression coverage for the 'blank company that will not stay deleted' bug."""

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import get_current_user
from app.database import Base, get_db
from app.routers import companies, companies_admin


class CompanyLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "lifecycle.db"
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=self.engine)
        self.session_factory = sessionmaker(bind=self.engine)

        app = FastAPI()
        app.include_router(companies.router)
        app.include_router(companies_admin.router)
        self.current_user = {"sub": "owner-a", "email": "a@example.com"}
        app.dependency_overrides[get_current_user] = lambda: self.current_user
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

    def _create(self, name, **overrides):
        response = self.client.post(
            "/api/companies",
            json={"name": name, "onboarded": True, **overrides},
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_deleted_company_is_not_recreated_by_reads(self):
        # A brand new account has no company and no blank row is manufactured.
        self.assertEqual(self.client.get("/api/companies").json(), [])

        first = self._create("First Venture")
        second = self._create("Second Venture")

        deleted = self.client.delete(
            f"/api/companies/{first['id']}?force=true"
        )
        self.assertEqual(deleted.status_code, 204, deleted.text)

        # Repeated "page reloads" must all see the same two-company-free state.
        for _ in range(3):
            listing = self.client.get("/api/companies").json()
            self.assertEqual([item["id"] for item in listing], [second["id"]])
            self.assertEqual(listing[0]["name"], "Second Venture")
            active = self.client.get("/api/company").json()
            self.assertEqual(active["id"], second["id"])
            self.assertEqual(active["name"], "Second Venture")

        # The last remaining company cannot be deleted out from under the user.
        blocked = self.client.delete(
            f"/api/companies/{second['id']}?force=true"
        )
        self.assertEqual(blocked.status_code, 409)

    def test_stale_active_company_header_is_rejected(self):
        company = self._create("Acme")
        other = self._create("Other")
        self.client.delete(f"/api/companies/{other['id']}?force=true")

        stale = self.client.get(
            "/api/company", headers={"X-Company-Id": str(other["id"])}
        )
        self.assertEqual(stale.status_code, 404)

        valid = self.client.get(
            "/api/company", headers={"X-Company-Id": str(company["id"])}
        )
        self.assertEqual(valid.status_code, 200)
        self.assertEqual(valid.json()["name"], "Acme")

    def test_onboarding_fields_are_persisted(self):
        company = self._create("My Startup", mission="Build useful things", stage="seed")
        self.assertTrue(company["onboarded"])

        updated = self.client.patch(
            f"/api/companies/{company['id']}",
            json={"name": "Renamed Startup", "onboarded": True},
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["name"], "Renamed Startup")
        self.assertTrue(updated.json()["onboarded"])

    def test_companies_are_isolated_per_user(self):
        owned = self._create("Private Co")

        self.current_user["sub"] = "owner-b"
        self.assertEqual(self.client.get("/api/companies").json(), [])
        missing = self.client.get(f"/api/companies/{owned['id']}")
        self.assertEqual(missing.status_code, 404)
        removed = self.client.delete(f"/api/companies/{owned['id']}?force=true")
        self.assertEqual(removed.status_code, 404)

        self.current_user["sub"] = "owner-a"
        self.assertEqual(
            [item["id"] for item in self.client.get("/api/companies").json()],
            [owned["id"]],
        )


if __name__ == "__main__":
    unittest.main()
