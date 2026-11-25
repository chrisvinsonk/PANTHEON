"""Programme 4/5 — Performance, executive scorecard and founder feedback."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..company import performance_snapshot
from ..database import get_db
from ..models import (
    AgentContribution,
    BoardMeeting,
    Company,
    ExecutiveFeedback,
)
from ..schemas import (
    ContributionReviewOut,
    ExecutiveFeedbackIn,
    ExecutiveFeedbackOut,
    PerformanceOut,
)
from ..scorecards import FEEDBACK_DIMENSIONS, build_scorecards, contribution_reviews
from ..tenancy import get_active_company

router = APIRouter(
    prefix="/api/performance",
    tags=["performance"],
    dependencies=[Depends(get_current_user)],
)


def _actor(user: dict | None) -> str:
    if not user:
        return "Founder"
    return str(user.get("email") or user.get("name") or "Founder")


def _feedback_out(row: ExecutiveFeedback) -> ExecutiveFeedbackOut:
    return ExecutiveFeedbackOut(
        id=row.id,
        role=row.role,
        dimension=row.dimension,
        rating=row.rating,
        meeting_id=row.meeting_id,
        contribution_id=row.contribution_id,
        notes=row.notes,
        actor=row.actor,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("", response_model=PerformanceOut)
def get_performance(
    db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    data = performance_snapshot(db, company.id)
    data.update(build_scorecards(db, company.id))
    return PerformanceOut.model_validate(data)


@router.get("/contributions", response_model=list[ContributionReviewOut])
def list_contributions(
    role: str | None = Query(default=None),
    meeting_id: int | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    if role and role not in {"CEO", "CFO", "CTO", "CSO"}:
        raise HTTPException(422, "Unknown executive role")
    return [
        ContributionReviewOut.model_validate(
            {
                **review,
                "feedback": [
                    _feedback_out(row) for row in review.get("feedback", [])
                ],
            }
        )
        for review in contribution_reviews(
            db, company.id, role=role, meeting_id=meeting_id, limit=limit
        )
    ]


@router.post("/feedback", response_model=ExecutiveFeedbackOut)
def submit_feedback(
    payload: ExecutiveFeedbackIn,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    if payload.dimension not in FEEDBACK_DIMENSIONS:
        raise HTTPException(422, "Unknown feedback dimension")
    contribution = None
    if payload.contribution_id is not None:
        contribution = (
            db.query(AgentContribution)
            .join(BoardMeeting, AgentContribution.meeting_id == BoardMeeting.id)
            .filter(
                AgentContribution.id == payload.contribution_id,
                BoardMeeting.company_id == company.id,
            )
            .first()
        )
        if contribution is None:
            raise HTTPException(404, "Contribution not found")
        if contribution.role != payload.role:
            raise HTTPException(422, "Feedback role does not match the contribution")
    meeting_id = payload.meeting_id
    if meeting_id is None and contribution is not None:
        meeting_id = contribution.meeting_id
    if meeting_id is not None and (
        db.query(BoardMeeting)
        .filter_by(id=meeting_id, company_id=company.id)
        .first()
        is None
    ):
        raise HTTPException(404, "Meeting not found")

    row = (
        db.query(ExecutiveFeedback)
        .filter_by(
            company_id=company.id,
            meeting_id=meeting_id,
            role=payload.role,
            dimension=payload.dimension,
        )
        .first()
    )
    if row is None:
        row = ExecutiveFeedback(
            role=payload.role,
            meeting_id=meeting_id,
            dimension=payload.dimension,
            company_id=company.id,
        )
        db.add(row)
    row.company_id = company.id
    row.contribution_id = payload.contribution_id
    row.rating = payload.rating
    row.notes = payload.notes
    row.actor = _actor(user)
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return _feedback_out(row)


@router.delete("/feedback/{feedback_id}", status_code=204)
def delete_feedback(
    feedback_id: int,
    db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    row = (
        db.query(ExecutiveFeedback)
        .filter_by(id=feedback_id, company_id=company.id)
        .first()
    )
    if row is None:
        raise HTTPException(404, "Feedback not found")
    db.delete(row)
    db.commit()
    return Response(status_code=204)
