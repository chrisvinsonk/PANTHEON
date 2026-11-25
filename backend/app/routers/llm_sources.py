import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session, joinedload

from ..auth import get_current_user
from ..config import get_settings
from ..database import get_db
from ..llm_config import (
    LLM_ROLES,
    PROVIDER_DEFAULTS,
    decrypt_api_key,
    encryption_key_ready,
    encrypt_api_key,
    validate_base_url,
)
from ..models import AgentLLMRoute, LLMSource
from ..schemas import (
    AgentLLMRouteOut,
    AgentLLMRoutesBulkSet,
    AgentLLMRouteSet,
    LLMModelsOut,
    LLMSettingsOut,
    LLMSourceCreate,
    LLMSourceOut,
    LLMSourceUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/llm",
    tags=["LLM sources"],
    dependencies=[Depends(get_current_user)],
)


def _require_encryption_key():
    if not encryption_key_ready():
        raise HTTPException(
            status_code=503,
            detail=(
                "LLM source management is unavailable. Configure a valid "
                "LLM_CONFIG_ENCRYPTION_KEY on the backend."
            ),
        )


def _source_out(source: LLMSource) -> LLMSourceOut:
    return LLMSourceOut(
        id=source.id,
        name=source.name,
        provider=source.provider,
        base_url=source.base_url,
        api_key_configured=bool(source.encrypted_api_key),
    )


def _get_source(db: Session, source_id: int) -> LLMSource:
    source = db.query(LLMSource).filter_by(id=source_id).first()
    if source is None:
        raise HTTPException(status_code=404, detail="LLM source not found.")
    return source


@router.get("/settings", response_model=LLMSettingsOut)
def get_llm_settings(db: Session = Depends(get_db)):
    settings = get_settings()
    sources = db.query(LLMSource).order_by(LLMSource.id.asc()).all()
    saved_routes = {
        route.role: route
        for route in db.query(AgentLLMRoute)
        .options(joinedload(AgentLLMRoute.source))
        .all()
    }
    routes = []
    for role in LLM_ROLES:
        route = saved_routes.get(role)
        if route:
            routes.append(
                AgentLLMRouteOut(
                    role=role,
                    source_id=route.source_id,
                    source_name=route.source.name,
                    provider=route.source.provider,
                    model_name=route.model_name,
                )
            )
        else:
            provider = settings.provider_for(role).lower()
            routes.append(
                AgentLLMRouteOut(
                    role=role,
                    source_id=None,
                    source_name="Environment configuration",
                    provider=provider,
                    model_name=settings.model_for(role),
                    environment_fallback=True,
                )
            )
    return LLMSettingsOut(
        encryption_key_ready=encryption_key_ready(),
        sources=[_source_out(source) for source in sources],
        routes=routes,
    )


@router.post("/sources", response_model=LLMSourceOut, status_code=201)
def create_llm_source(payload: LLMSourceCreate, db: Session = Depends(get_db)):
    _require_encryption_key()
    if not payload.name.strip():
        raise HTTPException(status_code=422, detail="A display name is required.")
    default = PROVIDER_DEFAULTS[payload.provider]
    base_url = payload.base_url or default["base_url"]
    if not base_url:
        raise HTTPException(
            status_code=422,
            detail="A base URL is required for a custom OpenAI-compatible source.",
        )
    try:
        base_url = validate_base_url(base_url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    api_key = payload.api_key.get_secret_value().strip() if payload.api_key else ""
    if default["category"] == "cloud" and not api_key:
        raise HTTPException(
            status_code=422,
            detail="An API key is required for hosted provider sources.",
        )
    source = LLMSource(
        name=payload.name.strip(),
        provider=payload.provider,
        base_url=base_url,
        encrypted_api_key=encrypt_api_key(api_key) if api_key else None,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return _source_out(source)


@router.patch("/sources/{source_id}", response_model=LLMSourceOut)
def update_llm_source(
    source_id: int,
    payload: LLMSourceUpdate,
    db: Session = Depends(get_db),
):
    _require_encryption_key()
    source = _get_source(db, source_id)
    changes = payload.model_dump(exclude_unset=True)
    if "api_key" in changes and payload.api_key is not None and payload.clear_api_key:
        raise HTTPException(
            status_code=422,
            detail="Provide a new API key or clear the saved key, not both.",
        )
    if payload.name is not None:
        if not payload.name.strip():
            raise HTTPException(status_code=422, detail="A display name is required.")
        source.name = payload.name.strip()
    if payload.base_url is not None:
        try:
            source.base_url = validate_base_url(payload.base_url)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    if payload.clear_api_key:
        if PROVIDER_DEFAULTS[source.provider]["category"] != "local":
            raise HTTPException(
                status_code=422,
                detail="Hosted provider sources must keep an API key configured.",
            )
        source.encrypted_api_key = None
    elif payload.api_key is not None:
        api_key = payload.api_key.get_secret_value().strip()
        if api_key:
            source.encrypted_api_key = encrypt_api_key(api_key)

    db.commit()
    db.refresh(source)
    return _source_out(source)


@router.delete("/sources/{source_id}", status_code=204)
def delete_llm_source(source_id: int, db: Session = Depends(get_db)):
    source = _get_source(db, source_id)
    if db.query(AgentLLMRoute.role).filter_by(source_id=source_id).first():
        raise HTTPException(
            status_code=409,
            detail="This source is assigned to one or more executives. Change those routes first.",
        )
    db.delete(source)
    db.commit()
    return Response(status_code=204)


@router.put("/routes/bulk", response_model=list[AgentLLMRouteOut])
def set_agent_llm_routes_bulk(
    payload: AgentLLMRoutesBulkSet,
    db: Session = Depends(get_db),
):
    _require_encryption_key()
    roles = list(dict.fromkeys(role.strip().upper() for role in payload.roles))
    if any(role not in LLM_ROLES for role in roles):
        raise HTTPException(
            status_code=422,
            detail=f"Roles must be selected from: {', '.join(LLM_ROLES)}.",
        )
    source = _get_source(db, payload.source_id)
    if (
        PROVIDER_DEFAULTS[source.provider]["category"] == "cloud"
        and not source.encrypted_api_key
    ):
        raise HTTPException(
            status_code=409,
            detail="Configure an API key for this hosted provider before assigning it.",
        )
    model_name = payload.model_name.strip()
    if not model_name:
        raise HTTPException(status_code=422, detail="A model ID is required.")

    existing_routes = {
        route.role: route
        for route in db.query(AgentLLMRoute)
        .filter(AgentLLMRoute.role.in_(roles))
        .all()
    }
    results = []
    for role in roles:
        route = existing_routes.get(role)
        if route is None:
            route = AgentLLMRoute(role=role)
            db.add(route)
        route.source = source
        route.model_name = model_name
        results.append(
            AgentLLMRouteOut(
                role=role,
                source_id=source.id,
                source_name=source.name,
                provider=source.provider,
                model_name=model_name,
            )
        )
    db.commit()
    return results

@router.put("/routes/{role}", response_model=AgentLLMRouteOut)
def set_agent_llm_route(
    role: str,
    payload: AgentLLMRouteSet,
    db: Session = Depends(get_db),
):
    _require_encryption_key()
    role = role.upper()
    if role not in LLM_ROLES:
        raise HTTPException(status_code=404, detail="Unknown executive role.")
    source = _get_source(db, payload.source_id)
    if (
        PROVIDER_DEFAULTS[source.provider]["category"] == "cloud"
        and not source.encrypted_api_key
    ):
        raise HTTPException(
            status_code=409,
            detail="Configure an API key for this hosted provider before assigning it.",
        )
    model_name = payload.model_name.strip()
    if not model_name:
        raise HTTPException(status_code=422, detail="A model ID is required.")
    route = db.query(AgentLLMRoute).filter_by(role=role).first()
    if route is None:
        route = AgentLLMRoute(role=role)
        db.add(route)
    route.source = source
    route.model_name = model_name
    db.commit()
    return AgentLLMRouteOut(
        role=role,
        source_id=source.id,
        source_name=source.name,
        provider=source.provider,
        model_name=model_name,
    )


@router.delete("/routes/{role}", status_code=204)
def clear_agent_llm_route(role: str, db: Session = Depends(get_db)):
    role = role.upper()
    if role not in LLM_ROLES:
        raise HTTPException(status_code=404, detail="Unknown executive role.")
    route = db.query(AgentLLMRoute).filter_by(role=role).first()
    if route:
        db.delete(route)
        db.commit()
    return Response(status_code=204)


@router.post("/sources/{source_id}/test", response_model=LLMModelsOut)
async def test_llm_source(source_id: int, db: Session = Depends(get_db)):
    source = _get_source(db, source_id)
    provider = source.provider
    source_defaults = PROVIDER_DEFAULTS[provider]
    try:
        api_key = (
            decrypt_api_key(source.encrypted_api_key)
            if source.encrypted_api_key
            else ("ollama" if provider == "ollama" else "lm-studio")
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    base_url = source.base_url.rstrip("/")
    params = None
    if provider == "anthropic":
        models_url = f"{base_url}/v1/models"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
        params = {"limit": 1000}
    elif provider == "google_gemini":
        models_url = f"{base_url}/v1beta/models"
        headers = {"x-goog-api-key": api_key}
        params = {"pageSize": 1000}
    else:
        models_url = f"{base_url}/models"
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(models_url, headers=headers, params=params)
    except httpx.RequestError as exc:
        logger.info("LLM source connectivity check failed for source %s.", source_id)
        raise HTTPException(
            status_code=502,
            detail="Could not reach the source. Check the URL and confirm it is reachable from the backend.",
        ) from exc

    if response.status_code in {401, 403}:
        raise HTTPException(
            status_code=502,
            detail="The source rejected the API key. Check the saved credentials.",
        )
    if response.status_code == 404:
        raise HTTPException(
            status_code=502,
            detail=(
                f"{source_defaults['label']} did not expose its expected model-list "
                "endpoint. Check the source URL and provider type."
            ),
        )
    if response.is_error:
        logger.info(
            "LLM source %s returned HTTP %s during its connectivity check.",
            source_id,
            response.status_code,
        )
        raise HTTPException(
            status_code=502,
            detail=f"The source returned HTTP {response.status_code} while listing models.",
        )
    try:
        body = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail="The source returned a response that was not valid JSON.",
        ) from exc

    if provider == "google_gemini":
        data = body.get("models") if isinstance(body, dict) else None
        model_ids = set()
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                supported_methods = item.get("supportedGenerationMethods")
                if (
                    not isinstance(supported_methods, list)
                    or "generateContent" not in supported_methods
                ):
                    continue
                model_id = item.get("baseModelId")
                if not isinstance(model_id, str):
                    model_name = item.get("name")
                    model_id = (
                        model_name.removeprefix("models/")
                        if isinstance(model_name, str)
                        else ""
                    )
                if model_id:
                    model_ids.add(model_id)
        models = sorted(model_ids)
    else:
        data = body.get("data") if isinstance(body, dict) else None
        models = sorted(
            {
                item["id"]
                for item in data
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            }
        ) if isinstance(data, list) else []
    if not isinstance(data, list):
        raise HTTPException(
            status_code=502,
            detail=f"{source_defaults['label']} returned an unexpected model-list response.",
        )
    return LLMModelsOut(models=models[:500])
