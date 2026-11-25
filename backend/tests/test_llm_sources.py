from contextlib import asynccontextmanager
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agents.graph import llm_for
from app.auth import get_current_user
from app.config import Settings
from app.database import Base, get_db
from app.llm_config import (
    decrypt_api_key,
    resolve_role_llm_configs,
    seed_environment_llm_sources,
)
from app.models import AgentLLMRoute, LLMSource
from app.routers import llm_sources


class FakeModelsResponse:
    status_code = 200
    is_error = False

    def json(self):
        return {"data": [{"id": "model-z"}, {"id": "model-a"}]}

class FakeAnthropicModelsResponse:
    status_code = 200
    is_error = False

    def json(self):
        return {"data": [{"id": "claude-sonnet"}, {"id": "claude-haiku"}]}

class FakeGeminiModelsResponse:
    status_code = 200
    is_error = False

    def json(self):
        return {
            "models": [
                {
                    "name": "models/gemini-flash-preview",
                    "baseModelId": "gemini-flash",
                    "supportedGenerationMethods": ["generateContent"],
                },
                {
                    "name": "models/gemini-embedding",
                    "baseModelId": "gemini-embedding",
                    "supportedGenerationMethods": ["embedContent"],
                },
            ]
        }


class FakeAsyncClient:
    last_request = None

    async def get(self, url, headers, params=None):
        FakeAsyncClient.last_request = (url, headers, params)
        if "anthropic.com" in url:
            return FakeAnthropicModelsResponse()
        if "generativelanguage.googleapis.com" in url:
            return FakeGeminiModelsResponse()
        return FakeModelsResponse()


@asynccontextmanager
async def fake_async_client(**kwargs):
    assert kwargs["timeout"] == 15.0
    yield FakeAsyncClient()


class LLMSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "llm-sources.db"
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        self.encryption_key = Fernet.generate_key().decode("ascii")
        self.settings = Settings(
            llm_config_encryption_key=self.encryption_key,
            local_base_url="http://localhost:1234/v1",
            local_api_key="lm-studio",
            local_model="local-model",
            cloud_base_url="https://api.openai.com/v1",
            cloud_api_key="",
            cloud_model="cloud-model",
        )
        self.settings_patch = patch("app.llm_config.get_settings", return_value=self.settings)
        self.settings_patch.start()

        app = FastAPI()
        app.include_router(llm_sources.router)
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

    def test_api_keys_are_encrypted_and_never_returned(self):
        secret = "provider-secret-value"
        response = self.client.post(
            "/api/llm/sources",
            json={"name": "Primary API", "provider": "openai", "api_key": secret},
        )
        self.assertEqual(response.status_code, 201)
        self.assertNotIn(secret, response.text)
        self.assertTrue(response.json()["api_key_configured"])

        db = self.session_factory()
        try:
            source = db.query(LLMSource).one()
            self.assertNotEqual(source.encrypted_api_key, secret)
            self.assertEqual(decrypt_api_key(source.encrypted_api_key), secret)
        finally:
            db.close()

    def test_routes_resolve_persisted_provider_and_model(self):
        source_response = self.client.post(
            "/api/llm/sources",
            json={
                "name": "LM Studio",
                "provider": "lm_studio",
                "base_url": "http://localhost:1234/v1",
            },
        )
        source_id = source_response.json()["id"]
        route_response = self.client.put(
            "/api/llm/routes/CEO",
            json={"source_id": source_id, "model_name": "qwen-local"},
        )
        self.assertEqual(route_response.status_code, 200)
        self.assertEqual(route_response.json()["model_name"], "qwen-local")

        db = self.session_factory()
        try:
            configs = resolve_role_llm_configs(db)
            self.assertEqual(configs["CEO"]["provider"], "local")
            self.assertEqual(configs["CEO"]["base_url"], "http://localhost:1234/v1")
            self.assertEqual(configs["CEO"]["model"], "qwen-local")
            self.assertEqual(configs["CEO"]["api_key"], "lm-studio")
            self.assertEqual(configs["CFO"]["model"], "local-model")
        finally:
            db.close()

    def test_assigned_source_cannot_be_deleted_until_route_is_cleared(self):
        source = self.client.post(
            "/api/llm/sources",
            json={"name": "LM Studio", "provider": "lm_studio"},
        ).json()
        self.client.put(
            "/api/llm/routes/BOARD",
            json={"source_id": source["id"], "model_name": "local-model"},
        )

        blocked = self.client.delete(f"/api/llm/sources/{source['id']}")
        self.assertEqual(blocked.status_code, 409)
        cleared = self.client.delete("/api/llm/routes/BOARD")
        self.assertEqual(cleared.status_code, 204)
        deleted = self.client.delete(f"/api/llm/sources/{source['id']}")
        self.assertEqual(deleted.status_code, 204)

    def test_bulk_route_applies_one_source_and_model_to_selected_roles(self):
        source = self.client.post(
            "/api/llm/sources",
            json={
                "name": "Groq",
                "provider": "groq",
                "api_key": "groq-test-key",
            },
        ).json()

        response = self.client.put(
            "/api/llm/routes/bulk",
            json={
                "source_id": source["id"],
                "model_name": "qwen/qwen3.8-27b",
                "roles": ["ceo", "CFO", "CTO", "CSO"],
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            [route["role"] for route in response.json()],
            ["CEO", "CFO", "CTO", "CSO"],
        )
        db = self.session_factory()
        try:
            configs = resolve_role_llm_configs(db)
            for role in ("CEO", "CFO", "CTO", "CSO"):
                self.assertEqual(configs[role]["source_provider"], "groq")
                self.assertEqual(configs[role]["model"], "qwen/qwen3.8-27b")
            self.assertEqual(
                configs["BOARD"]["source_name"],
                "Environment configuration",
            )
        finally:
            db.close()

    def test_source_connectivity_returns_model_ids_without_credentials(self):
        source = self.client.post(
            "/api/llm/sources",
            json={
                "name": "OpenRouter",
                "provider": "openrouter",
                "api_key": "do-not-return-this",
            },
        ).json()

        with patch("app.routers.llm_sources.httpx.AsyncClient", fake_async_client):
            response = self.client.post(f"/api/llm/sources/{source['id']}/test")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["models"], ["model-a", "model-z"])
        url, headers, params = FakeAsyncClient.last_request
        self.assertEqual(url, "https://openrouter.ai/api/v1/models")
        self.assertEqual(headers["Authorization"], "Bearer do-not-return-this")
        self.assertIsNone(params)
        self.assertNotIn("do-not-return-this", response.text)

    def test_anthropic_source_uses_native_models_api(self):
        source = self.client.post(
            "/api/llm/sources",
            json={
                "name": "Claude",
                "provider": "anthropic",
                "api_key": "anthropic-test-key",
            },
        ).json()

        with patch("app.routers.llm_sources.httpx.AsyncClient", fake_async_client):
            response = self.client.post(f"/api/llm/sources/{source['id']}/test")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["models"], ["claude-haiku", "claude-sonnet"])
        url, headers, params = FakeAsyncClient.last_request
        self.assertEqual(url, "https://api.anthropic.com/v1/models")
        self.assertEqual(headers["x-api-key"], "anthropic-test-key")
        self.assertEqual(headers["anthropic-version"], "2023-06-01")
        self.assertEqual(params, {"limit": 1000})

    def test_gemini_source_lists_only_generation_models_using_native_auth(self):
        source = self.client.post(
            "/api/llm/sources",
            json={
                "name": "Gemini",
                "provider": "google_gemini",
                "api_key": "google-test-key",
            },
        ).json()

        with patch("app.routers.llm_sources.httpx.AsyncClient", fake_async_client):
            response = self.client.post(f"/api/llm/sources/{source['id']}/test")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["models"], ["gemini-flash"])
        url, headers, params = FakeAsyncClient.last_request
        self.assertEqual(
            url,
            "https://generativelanguage.googleapis.com/v1beta/models",
        )
        self.assertEqual(headers["x-goog-api-key"], "google-test-key")
        self.assertEqual(params, {"pageSize": 1000})

    def test_source_settings_require_encryption_key_before_writes(self):
        invalid_settings = Settings(llm_config_encryption_key="")
        with patch("app.llm_config.get_settings", return_value=invalid_settings):
            response = self.client.post(
                "/api/llm/sources",
                json={"name": "LM Studio", "provider": "lm_studio"},
            )
        self.assertEqual(response.status_code, 503)
        self.assertIn("LLM_CONFIG_ENCRYPTION_KEY", response.json()["detail"])

    def test_runtime_uses_run_pinned_source_configuration(self):
        config = {
            "configurable": {
                "llm_configs": {
                    "CEO": {
                        "provider": "local",
                        "model": "pinned-model",
                        "base_url": "http://127.0.0.1:1234/v1",
                        "api_key": "local-key",
                    }
                }
            }
        }
        with patch("app.agents.graph.ChatOpenAI") as chat:
            llm, provider, model = llm_for("CEO", config)

        self.assertIsNotNone(llm)
        self.assertEqual((provider, model), ("local", "pinned-model"))
        chat.assert_called_once_with(
            model="pinned-model",
            base_url="http://127.0.0.1:1234/v1",
            api_key="local-key",
            temperature=0.2,
            max_retries=1,
        )

    def test_native_provider_routes_use_their_langchain_adapters(self):
        base_config = {
            "provider": "cloud",
            "model": "provider-model",
            "base_url": "https://unused.example",
            "api_key": "provider-key",
        }
        cases = (
            (
                "anthropic",
                "ChatAnthropic",
                {"base_url": "https://unused.example", "max_retries": 2},
            ),
            (
                "google_gemini",
                "ChatGoogleGenerativeAI",
                {"temperature": 0.2, "vertexai": False},
            ),
        )
        for provider_id, adapter_name, expected_options in cases:
            with self.subTest(provider=provider_id):
                config = {
                    "configurable": {
                        "llm_configs": {
                            "CEO": {
                                **base_config,
                                "source_provider": provider_id,
                            }
                        }
                    }
                }
                module_name = {
                    "ChatAnthropic": "langchain_anthropic",
                    "ChatGoogleGenerativeAI": "langchain_google_genai",
                }[adapter_name]
                with patch(f"{module_name}.{adapter_name}") as adapter:
                    llm, provider, model = llm_for("CEO", config)

                self.assertIsNotNone(llm)
                self.assertEqual((provider, model), (provider_id, "provider-model"))
                adapter.assert_called_once_with(
                    model="provider-model",
                    api_key="provider-key",
                    **expected_options,
                )

    def test_missing_native_adapter_reports_environment_setup_error(self):
        config = {
            "configurable": {
                "llm_configs": {
                    "CEO": {
                        "provider": "cloud",
                        "source_provider": "anthropic",
                        "model": "claude-model",
                        "base_url": "https://api.anthropic.com",
                        "api_key": "provider-key",
                    }
                }
            }
        }
        with patch.dict(sys.modules, {"langchain_anthropic": None}):
            with self.assertRaisesRegex(RuntimeError, "Install requirements.txt"):
                llm_for("CEO", config)

    def test_ollama_routes_as_local_openai_compatible_source(self):
        source = self.client.post(
            "/api/llm/sources",
            json={"name": "Ollama", "provider": "ollama"},
        ).json()
        self.client.put(
            "/api/llm/routes/CEO",
            json={"source_id": source["id"], "model_name": "qwen3:8b"},
        )
        db = self.session_factory()
        try:
            config = resolve_role_llm_configs(db)["CEO"]
        finally:
            db.close()

        self.assertEqual(config["provider"], "local")
        self.assertEqual(config["source_provider"], "ollama")
        self.assertEqual(config["base_url"], "http://localhost:11434/v1")
        self.assertEqual(config["api_key"], "ollama")
        with patch("app.agents.graph.ChatOpenAI") as chat:
            llm, provider, model = llm_for(
                "CEO",
                {"configurable": {"llm_configs": {"CEO": config}}},
            )

        self.assertIsNotNone(llm)
        self.assertEqual((provider, model), ("ollama", "qwen3:8b"))
        chat.assert_called_once_with(
            model="qwen3:8b",
            base_url="http://localhost:11434/v1",
            api_key="ollama",
            temperature=0.2,
            max_retries=1,
        )

    def test_environment_settings_seed_sources_and_routes_once(self):
        settings = Settings(
            llm_config_encryption_key=self.encryption_key,
            local_model="seeded-local-model",
            local_base_url="http://localhost:1234/v1",
            ceo_provider="local",
            cfo_provider="local",
            cto_provider="local",
            cso_provider="local",
            board_provider="local",
        )
        db = self.session_factory()
        try:
            with patch("app.llm_config.get_settings", return_value=settings):
                seed_environment_llm_sources(db)
                seed_environment_llm_sources(db)

            self.assertEqual(db.query(LLMSource).count(), 1)
            self.assertEqual(db.query(AgentLLMRoute).count(), 5)
            self.assertEqual(
                db.query(AgentLLMRoute)
                .filter_by(role="BOARD")
                .one()
                .model_name,
                "seeded-local-model",
            )
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
