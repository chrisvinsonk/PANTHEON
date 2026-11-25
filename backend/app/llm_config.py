from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session, joinedload

from .config import get_settings
from .models import AgentLLMRoute, LLMSource

LLM_ROLES = ("CEO", "CFO", "CTO", "CSO", "BOARD")

PROVIDER_DEFAULTS = {
    "lm_studio": {
        "label": "LM Studio",
        "base_url": "http://localhost:1234/v1",
        "category": "local",
    },
    "ollama": {
        "label": "Ollama",
        "base_url": "http://localhost:11434/v1",
        "category": "local",
    },
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "category": "cloud",
    },
    "anthropic": {
        "label": "Anthropic Claude",
        "base_url": "https://api.anthropic.com",
        "category": "cloud",
    },
    "google_gemini": {
        "label": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com",
        "category": "cloud",
    },
    "openrouter": {
        "label": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "category": "cloud",
    },
    "groq": {
        "label": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "category": "cloud",
    },
    "together": {
        "label": "Together AI",
        "base_url": "https://api.together.xyz/v1",
        "category": "cloud",
    },
    "fireworks": {
        "label": "Fireworks AI",
        "base_url": "https://api.fireworks.ai/inference/v1",
        "category": "cloud",
    },
    "mistral": {
        "label": "Mistral AI",
        "base_url": "https://api.mistral.ai/v1",
        "category": "cloud",
    },
    "deepseek": {
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "category": "cloud",
    },
    "xai": {
        "label": "xAI",
        "base_url": "https://api.x.ai/v1",
        "category": "cloud",
    },
    "cerebras": {
        "label": "Cerebras",
        "base_url": "https://api.cerebras.ai/v1",
        "category": "cloud",
    },
    "custom": {
        "label": "Custom OpenAI-compatible API",
        "base_url": "",
        "category": "cloud",
    },
}


def _fernet() -> Fernet:
    key = get_settings().llm_config_encryption_key
    if not key:
        raise RuntimeError(
            "LLM source management is disabled. Set LLM_CONFIG_ENCRYPTION_KEY "
            "on the backend and restart it."
        )
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise RuntimeError(
            "LLM_CONFIG_ENCRYPTION_KEY is invalid. Generate a Fernet key and "
            "restart the backend."
        ) from exc


def encryption_key_ready() -> bool:
    try:
        _fernet()
    except RuntimeError:
        return False
    return True


def encrypt_api_key(api_key: str) -> str:
    return _fernet().encrypt(api_key.encode("utf-8")).decode("ascii")


def decrypt_api_key(encrypted_api_key: str) -> str:
    try:
        return _fernet().decrypt(encrypted_api_key.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeEncodeError) as exc:
        raise RuntimeError(
            "The stored provider key could not be decrypted. Ensure "
            "LLM_CONFIG_ENCRYPTION_KEY matches the key used when it was saved."
        ) from exc


def validate_base_url(base_url: str) -> str:
    candidate = base_url.strip().rstrip("/")
    parsed = urlsplit(candidate)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Enter an HTTP or HTTPS API base URL without credentials or query parameters.")
    return candidate


def resolve_role_llm_configs(db: Session) -> dict[str, dict[str, str]]:
    settings = get_settings()
    resolved = {}
    for role in LLM_ROLES:
        provider = settings.provider_for(role).lower()
        resolved[role] = {
            "provider": provider,
            "model": settings.model_for(role),
            "base_url": (
                settings.local_base_url if provider == "local" else settings.cloud_base_url
            ),
            "api_key": (
                settings.local_api_key if provider == "local" else settings.cloud_api_key
            ),
            "source_name": "Environment configuration",
            "source_provider": provider,
        }

    routes = (
        db.query(AgentLLMRoute)
        .options(joinedload(AgentLLMRoute.source))
        .all()
    )
    for route in routes:
        source = route.source
        category = PROVIDER_DEFAULTS.get(source.provider, {}).get("category")
        if category is None:
            raise RuntimeError(f"Unsupported LLM source provider '{source.provider}'.")
        api_key = (
            decrypt_api_key(source.encrypted_api_key)
            if source.encrypted_api_key
            else (
                "ollama"
                if source.provider == "ollama"
                else "lm-studio" if category == "local" else ""
            )
        )
        resolved[route.role] = {
            "provider": category,
            "source_provider": source.provider,
            "model": route.model_name,
            "base_url": source.base_url,
            "api_key": api_key,
            "source_name": source.name,
        }
    return resolved


def seed_environment_llm_sources(db: Session) -> None:
    if db.query(LLMSource.id).first() or not encryption_key_ready():
        return

    settings = get_settings()
    sources: dict[tuple[str, str], LLMSource] = {}
    for role in LLM_ROLES:
        provider = settings.provider_for(role).lower()
        if provider not in {"local", "cloud"}:
            continue
        base_url = (
            settings.local_base_url if provider == "local" else settings.cloud_base_url
        )
        api_key = settings.local_api_key if provider == "local" else settings.cloud_api_key
        if provider == "cloud" and not api_key:
            continue

        preset = "lm_studio" if provider == "local" else "custom"
        source_key = (preset, base_url)
        source = sources.get(source_key)
        if source is None:
            source = LLMSource(
                name=(
                    "LM Studio (imported from environment)"
                    if provider == "local"
                    else "Cloud API (imported from environment)"
                ),
                provider=preset,
                base_url=validate_base_url(base_url),
                encrypted_api_key=encrypt_api_key(api_key) if api_key else None,
            )
            db.add(source)
            sources[source_key] = source

        db.add(
            AgentLLMRoute(
                role=role,
                source=source,
                model_name=settings.model_for(role),
            )
        )
    db.commit()
