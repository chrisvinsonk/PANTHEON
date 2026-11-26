"""Multi-company workspace administration.

A founder can operate several companies from one console. Each company owns
its own profile and its own scoped records (conclaves, evidence, decisions,
feedback and operational artifacts). The active company is selected per request
with the ``X-Company-Id`` header.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..company import company_status, seed_company_profile, serialize_company, touch
from ..database import get_db
from ..models import (
    AgentContribution,
    ApprovalEvent,
    BoardMeeting,
    BoardResolution,
    Company,
    DecisionRecord,
    EvidenceRecord,
    ExecutiveFeedback,
    MeetingEvidenceLink,
    MeetingRunCheckpoint,
    MeetingRunEvent,
    OperationalArtifact,
    OperationalEvent,
)
from ..schemas import CompanyCreate, CompanyProfileOut, CompanyUpdate

router = APIRouter(
    prefix="/api/companies",
    tags=["companies"],
    dependencies=[Depends(get_current_user)],
)


def _profile(db: Session, company: Company) -> CompanyProfileOut:
    status = company_status(db, company)
    payload = serialize_company(company)
    payload["counts"] = status["counts"]
    return CompanyProfileOut.model_validate(payload)


def _accessible_company(db: Session, company_id: int, user_id: str) -> Company:
    """Fetch a company the caller owns (or a legacy unowned company they adopt)."""
    company = db.get(Company, company_id)
    if company is None or not (
        company.owner_user_id is None or company.owner_user_id == user_id
    ):
        raise HTTPException(404, "Company not found")
    if company.owner_user_id is None:
        company.owner_user_id = user_id
        db.commit()
    return company


def _visible_company_count(db: Session, user_id: str) -> int:
    """Companies the caller can see: their own plus unclaimed legacy rows."""
    return (
        db.query(Company)
        .filter(
            or_(Company.owner_user_id == user_id, Company.owner_user_id.is_(None))
        )
        .count()
    )


def _scoped_ids(db: Session, company_id: int) -> tuple[list[int], list[int]]:
    meeting_ids = [
        row[0]
        for row in db.query(BoardMeeting.id)
        .filter(BoardMeeting.company_id == company_id)
        .all()
    ]
    decision_ids = [
        row[0]
        for row in db.query(DecisionRecord.id)
        .filter(DecisionRecord.company_id == company_id)
        .all()
    ]
    return meeting_ids, decision_ids


def _delete_company_data(db: Session, company_id: int) -> None:
    meeting_ids, _ = _scoped_ids(db, company_id)
    artifact_ids = [
        row[0]
        for row in db.query(OperationalArtifact.id)
        .filter(OperationalArtifact.company_id == company_id)
        .all()
    ]
    if artifact_ids:
        db.query(OperationalEvent).filter(
            OperationalEvent.artifact_id.in_(artifact_ids)
        ).delete(synchronize_session=False)
    db.query(OperationalArtifact).filter(
        OperationalArtifact.company_id == company_id
    ).delete(synchronize_session=False)
    db.query(ExecutiveFeedback).filter(
        ExecutiveFeedback.company_id == company_id
    ).delete(synchronize_session=False)
    if meeting_ids:
        db.query(ApprovalEvent).filter(
            ApprovalEvent.meeting_id.in_(meeting_ids)
        ).delete(synchronize_session=False)
        db.query(AgentContribution).filter(
            AgentContribution.meeting_id.in_(meeting_ids)
        ).delete(synchronize_session=False)
        db.query(MeetingRunCheckpoint).filter(
            MeetingRunCheckpoint.meeting_id.in_(meeting_ids)
        ).delete(synchronize_session=False)
        db.query(MeetingRunEvent).filter(
            MeetingRunEvent.meeting_id.in_(meeting_ids)
        ).delete(synchronize_session=False)
        db.query(MeetingEvidenceLink).filter(
            MeetingEvidenceLink.meeting_id.in_(meeting_ids)
        ).delete(synchronize_session=False)
        db.query(BoardResolution).filter(
            BoardResolution.meeting_id.in_(meeting_ids)
        ).delete(synchronize_session=False)
    db.query(DecisionRecord).filter(
        DecisionRecord.company_id == company_id
    ).delete(synchronize_session=False)
    db.query(EvidenceRecord).filter(
        EvidenceRecord.company_id == company_id
    ).delete(synchronize_session=False)
    if meeting_ids:
        db.query(BoardMeeting).filter(
            BoardMeeting.id.in_(meeting_ids)
        ).delete(synchronize_session=False)


@router.get("", response_model=list[CompanyProfileOut])
def list_companies(
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    user_id = user.get("sub")
    companies = (
        db.query(Company)
        .filter(Company.owner_user_id == user_id)
        .order_by(Company.id.asc())
        .all()
    )
    if not companies:
        # Adopt a legacy unowned company only when there is exactly one and the
        # user has none of their own. Never mass-assign rows across accounts and
        # never manufacture an empty company here.
        unowned = (
            db.query(Company)
            .filter(Company.owner_user_id.is_(None))
            .order_by(Company.id.asc())
            .all()
        )
        if len(unowned) == 1:
            unowned[0].owner_user_id = user_id
            db.commit()
            companies = unowned
    return [_profile(db, company) for company in companies]


@router.post("", response_model=CompanyProfileOut, status_code=201)
def create_company(
    payload: CompanyCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    company = seed_company_profile(
        db,
        name=payload.name.strip(),
        mission=payload.mission.strip(),
        strategic_context=payload.strategic_context.strip(),
        owner=payload.owner.strip() or "Founder",
        owner_user_id=user.get("sub"),
        stage=payload.stage.strip(),
        include_starters=payload.seed_starters,
        onboarded=payload.onboarded,
    )
    return _profile(db, company)


@router.get("/{company_id}", response_model=CompanyProfileOut)
def get_company(
    company_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    company = _accessible_company(db, company_id, user.get("sub"))
    return _profile(db, company)


@router.patch("/{company_id}", response_model=CompanyProfileOut)
def update_company(
    company_id: int,
    payload: CompanyUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    company = _accessible_company(db, company_id, user.get("sub"))
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(company, field, value)
    touch(company)
    db.commit()
    db.refresh(company)
    return _profile(db, company)


@router.delete("/{company_id}", status_code=204)
def delete_company(
    company_id: int,
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    user_id = user.get("sub")
    company = _accessible_company(db, company_id, user_id)
    if _visible_company_count(db, user_id) <= 1:
        raise HTTPException(409, "Keep at least one company. Create another before deleting this one.")
    if not force:
        status = company_status(db, company)
        counts = status["counts"]
        has_records = any(
            counts.get(key, 0)
            for key in ("meetings_total", "decisions_total", "evidence_total")
        )
        artifacts = (
            db.query(OperationalArtifact)
            .filter(OperationalArtifact.company_id == company_id)
            .count()
        )
        if has_records or artifacts:
            raise HTTPException(
                409,
                "This company still has records. Archive them or delete with force=true.",
            )
    _delete_company_data(db, company_id)
    db.delete(company)
    db.commit()
    return Response(status_code=204)
