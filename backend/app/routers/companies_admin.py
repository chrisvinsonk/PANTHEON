"""Multi-company workspace administration.

A founder can operate several companies from one console. Each company owns
its own profile and its own scoped records (conclaves, evidence, decisions,
feedback and operational artifacts). The active company is selected per request
with the ``X-Company-Id`` header.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..company import company_status, serialize_company, touch
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
from ..tenancy import seed_company_profile

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
def list_companies(db: Session = Depends(get_db)):
    companies = db.query(Company).order_by(Company.id.asc()).all()
    if not companies:
        companies = [ensure_default_company(db)]
    return [_profile(db, company) for company in companies]


@router.post("", response_model=CompanyProfileOut, status_code=201)
def create_company(payload: CompanyCreate, db: Session = Depends(get_db)):
    company = seed_company_profile(
        db,
        name=payload.name.strip(),
        mission=payload.mission.strip(),
        strategic_context=payload.strategic_context.strip(),
        owner=payload.owner.strip() or "Founder",
        stage=payload.stage.strip(),
        include_starters=payload.seed_starters,
    )
    return _profile(db, company)


@router.get("/{company_id}", response_model=CompanyProfileOut)
def get_company(company_id: int, db: Session = Depends(get_db)):
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "Company not found")
    return _profile(db, company)


@router.patch("/{company_id}", response_model=CompanyProfileOut)
def update_company(
    company_id: int,
    payload: CompanyUpdate,
    db: Session = Depends(get_db),
):
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "Company not found")
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
):
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "Company not found")
    if db.query(Company).count() <= 1:
        raise HTTPException(409, "The workspace must keep at least one company")
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


def ensure_default_company(db: Session) -> Company:
    from ..company import ensure_company

    return ensure_company(db)
