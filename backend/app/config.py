from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    app_name: str = "THE PANTHEON"
    app_env: str = "development"
    # Local runs use the Docker Postgres in backend/docker-compose.yml. Real
    # environment variables (Vercel dashboard) override this for deployments.
    # Neon's repo-root .env.local is deliberately NOT loaded here, so a fresh
    # clone can never pick up the maintainer's hosted database.
    database_url: str = (
        "postgresql+psycopg://companyos:change-me-before-use@localhost:5433/companyos"
    )
    # Optional direct connection for migrations/admin jobs.
    database_url_unpooled: str = ""
    api_cors_origins: str = "*"
    clerk_issuer: str = ""
    llm_config_encryption_key: str = ""
    local_base_url: str = "http://localhost:1234/v1"
    local_api_key: str = "lm-studio"
    local_model: str = "qwen2.5-coder-7b-instruct-mlx"
    cloud_base_url: str = "https://api.openai.com/v1"
    cloud_api_key: str = ""
    cloud_model: str = "gpt-4.1-mini"
    ceo_provider: str = "local"
    cfo_provider: str = "local"
    cto_provider: str = "local"
    cso_provider: str = "local"
    board_provider: str = "local"
    ceo_model: str = ""
    cfo_model: str = ""
    cto_model: str = ""
    cso_model: str = ""
    board_model: str = ""
    agent_concurrency: int = 1
    progress_initial_agent_seconds: int = 60
    board_synthesis_max_input_chars: int = Field(default=6000, ge=1024)
    allow_external_actions: bool = False

    def provider_for(self, role: str) -> str:
        return getattr(self, f"{role.lower()}_provider", self.board_provider)

    def model_for(self, role: str) -> str:
        override = getattr(self, f"{role.lower()}_model", "")
        return override or (self.local_model if self.provider_for(role) == "local" else self.cloud_model)

    @property
    def cors_origins(self):
        origins = [x.strip() for x in self.api_cors_origins.split(",") if x.strip()]
        return ["*"] if "*" in origins else origins

@lru_cache
def get_settings():
    return Settings()
