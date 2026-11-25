"""Programme 6 — Controlled operational capabilities API.

Draft generation, explicit submission and founder approval. No endpoint
performs an external action.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import get_settings
from ..database import get_db
from ..models import (
    BoardMeeting,
    Company,
    DecisionRecord,
    OperationalArtifact,
    OperationalEvent,
)
from ..operations import CAPABILITIES, CAPABILITY_BY_KIND, generate, policy
from ..schemas import (
    CapabilitiesOut,
    CapabilityOut,
    OperationalArtifactCreate,
    OperationalArtifactOut,
    OperationalCommentIn,
)
from ..tenancy import get_active_company

router = APIRouter(
    prefix="/api/operations",
    tags=["operations"],
    dependencies=[Depends(get_current_user)],
)

EDITABLE_STATUSES = {"draft", "rejected"}
PENDING_STATUS = "pending_approval"


def _actor(user: dict | None) -> str:
    if not user:
        return "Founder"
    return str(user.get("email") or user.get("name") or user.get("sub") or "Founder")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize(artifact: OperationalArtifact) -> dict:
    events = sorted(artifact_events(artifact), key=lambda event: event.created_at)
    return {
        "id": artifact.id,
        "kind": artifact.kind,
        "title": artifact.title,
        "brief": artifact.brief,
        "status": artifact.status,
        "payload": artifact.payload or {},
        "permissions": artifact.permissions or {},
        "meeting_id": artifact.meeting_id,
        "decision_id": artifact.decision_id,
        "created_by": artifact.created_by,
        "approved_by": artifact.approved_by,
        "approved_at": artifact.approved_at,
        "rejection_reason": artifact.rejection_reason,
        "created_at": artifact.created_at,
        "updated_at": artifact.updated_at,
        "events": [
            {
                "id": event.id,
                "action": event.action,
                "actor": event.actor,
                "comments": event.comments,
                "created_at": event.created_at,
            }
            for event in events
        ],
    }


def artifact_events(artifact: OperationalArtifact) -> list[OperationalEvent]:
    # Events are loaded explicitly by the query helpers below.
    return list(getattr(artifact, "_events", []) or [])


def _load(
    db: Session, artifact_id: int, company_id: int | None = None
) -> OperationalArtifact:
    query = db.query(OperationalArtifact).filter_by(id=artifact_id)
    if company_id is not None:
        query = query.filter(OperationalArtifact.company_id == company_id)
    artifact = query.first()
    if artifact is None:
        raise HTTPException(404, "Operational artifact not found")
    events = (
        db.query(OperationalEvent)
        .filter_by(artifact_id=artifact.id)
        .order_by(OperationalEvent.created_at.asc())
        .all()
    )
    artifact._events = events
    return artifact


def _record(
    db: Session,
    artifact: OperationalArtifact,
    action: str,
    actor: str,
    comments: str = "",
) -> None:
    db.add(
        OperationalEvent(
            artifact_id=artifact.id,
            action=action,
            actor=actor,
            comments=comments,
        )
    )


def _permissions(kind: str, external_requested: bool) -> dict:
    capability = CAPABILITY_BY_KIND[kind]
    return {
        "scopes": [capability["permission"]],
        "external": bool(capability["external"] or external_requested),
        "external_requested": external_requested,
        "approval_required": True,
    }


@router.get("/capabilities", response_model=CapabilitiesOut)
def list_capabilities():
    settings = get_settings()
    external_enabled = settings.allow_external_actions
    return {
        "capabilities": [
            CapabilityOut(
                **capability,
                approval_required=True,
                enabled=True if not capability["external"] else external_enabled,
            )
            for capability in CAPABILITIES
        ],
        "policy": policy(external_enabled),
    }


@router.get("/artifacts", response_model=list[OperationalArtifactOut])
def list_artifacts(
    status: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    query = (
        db.query(OperationalArtifact)
        .filter(OperationalArtifact.company_id == company.id)
        .order_by(OperationalArtifact.created_at.desc())
    )
    if status:
        query = query.filter(OperationalArtifact.status == status)
    if kind:
        query = query.filter(OperationalArtifact.kind == kind)
    return [
        _serialize(_load(db, item.id, company.id))
        for item in query.limit(limit).all()
    ]


@router.post("/artifacts", response_model=OperationalArtifactOut, status_code=201)
def create_artifact(
    payload: OperationalArtifactCreate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    settings = get_settings()
    if payload.external_actions and not settings.allow_external_actions:
        raise HTTPException(
            403,
            "External actions are disabled for this instance. Stop at an internal draft "
            "until explicit instance permission is granted.",
        )
    if payload.meeting_id is not None and (
        db.query(BoardMeeting)
        .filter_by(id=payload.meeting_id, company_id=company.id)
        .first()
        is None
    ):
        raise HTTPException(404, "Meeting not found")
    if payload.decision_id is not None and (
        db.query(DecisionRecord)
        .filter_by(id=payload.decision_id, company_id=company.id)
        .first()
        is None
    ):
        raise HTTPException(404, "Decision not found")

    artifact = OperationalArtifact(
        company_id=company.id,
        kind=payload.kind,
        title=payload.title,
        brief=payload.brief,
        status="draft",
        payload=generate(db, company, payload.kind, payload.title, payload.brief),
        permissions=_permissions(payload.kind, payload.external_actions),
        meeting_id=payload.meeting_id,
        decision_id=payload.decision_id,
        created_by=_actor(user),
    )
    db.add(artifact)
    db.flush()
    _record(db, artifact, "generated", _actor(user), "Draft generated from company context.")
    db.commit()
    return _serialize(_load(db, artifact.id, company.id))


@router.get("/artifacts/{artifact_id}", response_model=OperationalArtifactOut)
def get_artifact(
    artifact_id: int,
    db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    return _serialize(_load(db, artifact_id, company.id))


@router.post("/artifacts/{artifact_id}/regenerate", response_model=OperationalArtifactOut)
def regenerate_artifact(
    artifact_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    artifact = _load(db, artifact_id, company.id)
    if artifact.status not in EDITABLE_STATUSES:
        raise HTTPException(409, "Only draft or rejected artifacts can be regenerated")
    artifact.payload = generate(db, company, artifact.kind, artifact.title, artifact.brief)
    artifact.status = "draft"
    artifact.rejection_reason = ""
    _record(db, artifact, "regenerated", _actor(user))
    db.commit()
    return _serialize(_load(db, artifact.id, company.id))


@router.post("/artifacts/{artifact_id}/submit", response_model=OperationalArtifactOut)
def submit_artifact(
    artifact_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    artifact = _load(db, artifact_id, company.id)
    if artifact.status not in EDITABLE_STATUSES:
        raise HTTPException(409, "Only draft or rejected artifacts can be submitted")
    artifact.status = PENDING_STATUS
    _record(db, artifact, "submitted", _actor(user), "Submitted for founder approval.")
    db.commit()
    return _serialize(_load(db, artifact.id, company.id))


@router.post("/artifacts/{artifact_id}/approve", response_model=OperationalArtifactOut)
def approve_artifact(
    artifact_id: int,
    payload: OperationalCommentIn | None = None,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    artifact = _load(db, artifact_id, company.id)
    if artifact.status != PENDING_STATUS:
        raise HTTPException(409, "Only artifacts pending approval can be approved")
    artifact.status = "approved"
    artifact.approved_by = _actor(user)
    artifact.approved_at = _now()
    _record(
        db,
        artifact,
        "approved",
        _actor(user),
        (payload.comments if payload else "") or "Approved for internal use.",
    )
    db.commit()
    return _serialize(_load(db, artifact.id, company.id))


@router.post("/artifacts/{artifact_id}/reject", response_model=OperationalArtifactOut)
def reject_artifact(
    artifact_id: int,
    payload: OperationalCommentIn | None = None,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    artifact = _load(db, artifact_id, company.id)
    if artifact.status != PENDING_STATUS:
        raise HTTPException(409, "Only artifacts pending approval can be rejected")
    artifact.status = "rejected"
    artifact.approved_by = None
    artifact.approved_at = None
    artifact.rejection_reason = (payload.comments if payload else "") or "Rejected by founder."
    _record(db, artifact, "rejected", _actor(user), artifact.rejection_reason)
    db.commit()
    return _serialize(_load(db, artifact.id, company.id))


@router.delete("/artifacts/{artifact_id}", status_code=204)
def delete_artifact(
    artifact_id: int,
    db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    artifact = _load(db, artifact_id, company.id)
    if artifact.status not in EDITABLE_STATUSES:
        raise HTTPException(409, "Only draft or rejected artifacts can be deleted")
    db.query(OperationalEvent).filter_by(artifact_id=artifact.id).delete()
    db.delete(artifact)
    db.commit()
    return Response(status_code=204)
