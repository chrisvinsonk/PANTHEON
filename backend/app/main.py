from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from .auth import get_current_user
from .config import get_settings
from .database import (
    Base,
    backfill_company_scope,
    engine,
    ensure_database_compatibility,
    SessionLocal,
)
from .seed import seed_defaults
from .models import Executive
from .schemas import ExecutiveOut
from .llm_config import seed_environment_llm_sources
from .routers.llm_sources import router as llm_sources_router
from .routers.evidence import evidence_router, research_router
from .routers.meetings import recover_interrupted_runs, router as meetings_router
from .routers.decisions import router as decisions_router
from .routers.companies import router as companies_router
from .routers.companies_admin import router as companies_admin_router
from .routers.performance import router as performance_router
from .routers.operations import router as operations_router

settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "A divine council of executive agents — CEO, CFO, CTO, and CSO — "
        "deliberate independently on an agenda, challenge one another, and the "
        "Pantheon Chair synthesizes a recommendation. The Founder alone records "
        "the final decree."
    ),
    contact={
        "name": "THE PANTHEON",
        "url": "https://github.com/the-pantheon",
    },
    license_info={
        "name": "Prototype — internal use only",
    },
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/api/openapi.json",
    openapi_tags=[
        {"name": "health", "description": "Service health checks."},
        {"name": "executives", "description": "Executive roster (CEO, CFO, CTO, CSO)."},
        {"name": "board meetings", "description": "Board meeting lifecycle: create, run deliberation, record decisions."},
        {"name": "evidence register", "description": "Source-backed company claims and their provenance, classification, quality, and dispute state."},
        {"name": "research", "description": "Search indexed biomedical literature, trial records, FDA device records, and optional web sources. Results are discovery leads, not verified evidence."},
        {"name": "company workspace", "description": "The active company's context object: mission, strategic priorities, constraints, financial assumptions, approved knowledge, governance and ownership."},
        {"name": "companies", "description": "Multi-company workspace: list, create, edit and retire company profiles. Select the active company with the X-Company-Id header."},
        {"name": "performance", "description": "Executive quality, the seven-dimension scorecard, and founder feedback on individual contributions."},
        {"name": "operations", "description": "Controlled operational capabilities: draft project plans, models, documents, tasks and reviews. Approval is required; no external action is performed."},
    ],
)
app.add_middleware(
    CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=False,
    allow_methods=["*"], allow_headers=["*"]
)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
    return response


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    openapi_schema["info"]["x-logo"] = {"url": "https://fastapi.tiangolo.com/img/logo-margin/logo-teal.png"}
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    ensure_database_compatibility(engine)
    db = SessionLocal()
    try:
        # Never seed an empty company at startup: on an ephemeral serverless
        # filesystem that blank row reappears on every cold start and looks
        # like a company the user cannot delete.
        recover_interrupted_runs(db)
    finally:
        db.close()

@app.get("/api/health", tags=["health"])
def health():
    return {"status": "ok", "service": settings.app_name, "environment": settings.app_env}

@app.get(
    "/api/executives",
    response_model=list[ExecutiveOut],
    tags=["executives"],
    dependencies=[Depends(get_current_user)],
)
def executives():
    db = SessionLocal()
    try:
        return db.query(Executive).order_by(Executive.role).all()
    finally:
        db.close()

app.include_router(meetings_router)
app.include_router(llm_sources_router)
app.include_router(evidence_router)
app.include_router(research_router)
app.include_router(decisions_router)
app.include_router(companies_router)
app.include_router(companies_admin_router)
app.include_router(performance_router)
app.include_router(operations_router)
