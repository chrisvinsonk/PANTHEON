import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient
from jwt.exceptions import PyJWKClientConnectionError

from app.auth import get_current_user
from app.config import Settings
from app.main import app

ISSUER = "https://fair-panther-4310.clerk.accounts.dev"
ALLOWED_ORIGIN = "http://localhost:5173"


class AuthenticationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.settings = Settings(
            clerk_issuer=ISSUER,
            api_cors_origins=ALLOWED_ORIGIN,
        )

    def make_token(self, signing_key=None, **overrides):
        now = datetime.now(timezone.utc)
        claims = {
            "iss": ISSUER,
            "sub": "user_test",
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "azp": ALLOWED_ORIGIN,
        }
        claims.update(overrides)
        return jwt.encode(claims, signing_key or self.private_key, algorithm="RS256")

    def authenticate(self, token, settings=None):
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        with (
            patch("app.auth.get_settings", return_value=settings or self.settings),
            patch("app.auth.get_jwks_client") as get_jwks_client,
        ):
            get_jwks_client.return_value.get_signing_key_from_jwt.return_value.key = (
                self.private_key.public_key()
            )
            return get_current_user(credentials)

    def test_accepts_valid_token_for_allowed_origin(self):
        claims = self.authenticate(self.make_token())
        self.assertEqual(claims["sub"], "user_test")

    def test_rejects_missing_credentials(self):
        with patch("app.auth.get_settings", return_value=self.settings):
            with self.assertRaises(HTTPException) as error:
                get_current_user(None)
        self.assertEqual(error.exception.status_code, 401)

    def test_rejects_token_from_another_origin(self):
        with self.assertRaises(HTTPException) as error:
            self.authenticate(self.make_token(azp="https://attacker.example"))
        self.assertEqual(error.exception.status_code, 401)

    def test_accepts_any_origin_when_cors_is_configured_as_wildcard(self):
        settings = Settings(clerk_issuer=ISSUER, api_cors_origins="*")
        claims = self.authenticate(
            self.make_token(azp="https://company-os-re-fe.onrender.com"),
            settings,
        )
        self.assertEqual(claims["sub"], "user_test")
        self.assertEqual(settings.cors_origins, ["*"])

    def test_rejects_token_from_another_issuer(self):
        with self.assertRaises(HTTPException) as error:
            self.authenticate(self.make_token(iss="https://other.example"))
        self.assertEqual(error.exception.status_code, 401)

    def test_rejects_expired_token(self):
        expired = datetime.now(timezone.utc) - timedelta(minutes=1)
        with self.assertRaises(HTTPException) as error:
            self.authenticate(self.make_token(exp=expired))
        self.assertEqual(error.exception.status_code, 401)

    def test_rejects_invalid_signature(self):
        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        with self.assertRaises(HTTPException) as error:
            self.authenticate(self.make_token(signing_key=other_key))
        self.assertEqual(error.exception.status_code, 401)

    def test_returns_service_unavailable_if_jwks_cannot_be_fetched(self):
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=self.make_token(),
        )
        with (
            patch("app.auth.get_settings", return_value=self.settings),
            patch("app.auth.get_jwks_client") as get_jwks_client,
        ):
            get_jwks_client.return_value.get_signing_key_from_jwt.side_effect = (
                PyJWKClientConnectionError("Clerk is unavailable")
            )
            with self.assertRaises(HTTPException) as error:
                get_current_user(credentials)
        self.assertEqual(error.exception.status_code, 503)

    def test_fails_closed_when_issuer_is_not_configured(self):
        settings = Settings(clerk_issuer="")
        with patch("app.auth.get_settings", return_value=settings):
            with self.assertRaises(HTTPException) as error:
                get_current_user(None)
        self.assertEqual(error.exception.status_code, 503)


class ProtectedEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health_check_remains_public(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)

    def test_data_endpoints_reject_anonymous_requests(self):
        for path in ("/api/executives", "/api/meetings"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
