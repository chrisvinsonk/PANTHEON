import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session, joinedload

from ..auth import get_current_user
from ..database import get_db
from ..memory import (
    format_memory_context,
    is_review_due,
    merge_conditions,
    recall_decisions,
    score_decision,
    serialize_decision,
    sync_decision_from_meeting,
)
from ..models import (
    BoardMeeting,
    BoardResolution,
    Company,
    DecisionLifecycle,
    DecisionRecord,
)
from ..schemas import (
    DecisionRecordCreate,
    DecisionRecordOut,
    DecisionRecordUpdate,
    DecisionReviewIn,
    MemoryRecallOut,
    MemoryRecordOut,
)
from ..tenancy import get_active_company

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/decisions",
    tags=["decision register"],
    dependencies=[Depends(get_current_user)],
)

LIFECYCLE_VALUES = {item.value for item in DecisionLifecycle}


def _get_record(db: Session, decision_id: int) -> DecisionRecord | None:
    return (
        db.query(DecisionRecord)
        .options(joinedload(DecisionRecord.meeting))
        .filter_by(id=decision_id)
        .first()
    )


def _out(record: DecisionRecord) -> DecisionRecordOut:
    return DecisionRecordOut.model_validate(serialize_decision(record))


def _require_company(record: DecisionRecord | None, company: Company) -> DecisionRecord:
    if record is None or record.company_id != company.id:
        raise HTTPException(status_code=404, detail="Decision record not found.")
    return record


@router.get("", response_model=list[DecisionRecordOut])
def list_decisions(
    lifecycle: str | None = Query(default=None),
    review_due: bool | None = Query(default=None),
    q: str | None = Query(default=None, max_length=300),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    record_query = (
        db.query(DecisionRecord)
        .options(joinedload(DecisionRecord.meeting))
        .filter(DecisionRecord.company_id == company.id)
        .order_by(DecisionRecord.updated_at.desc())
    )
    if lifecycle:
        if lifecycle not in LIFECYCLE_VALUES:
            raise HTTPException(status_code=422, detail=f"lifecycle must be one of {sorted(LIFECYCLE_VALUES)}")
        record_query = record_query.filter(DecisionRecord.lifecycle == DecisionLifecycle(lifecycle))
    records = record_query.limit(limit).all()
    if review_due is not None:
        records = [record for record in records if is_review_due(record) == review_due]
    if q:
        needle = q.strip().lower()
        if needle:
            records = [
                record for record in records
                if needle in " ".join(
                    str(value) for value in (
                        record.decision,
                        record.rationale,
                        record.board_recommendation,
                        record.success_criteria,
                        record.actual_outcome,
                        record.review_notes,
                        record.owner,
                        " ".join(str(c.get("label", "")) for c in record.conditions or []),
                    )
                ).lower()
            ]
    return [_out(record) for record in records]


@router.get("/due", response_model=list[DecisionRecordOut])
def due_decisions(
    db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    records = (
        db.query(DecisionRecord)
        .options(joinedload(DecisionRecord.meeting))
        .filter(DecisionRecord.company_id == company.id)
        .order_by(DecisionRecord.review_date.asc().nullslast(), DecisionRecord.updated_at.desc())
        .limit(500)
        .all()
    )
    return [_out(record) for record in records if is_review_due(record)]


@router.get("/memory", response_model=MemoryRecallOut)
def recall_memory(
    q: str = Query(min_length=2, max_length=600),
    limit: int = Query(default=5, ge=1, le=10),
    exclude_meeting_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    records = recall_decisions(
        db, q, limit=limit, exclude_meeting_id=exclude_meeting_id, company_id=company.id
    )
    memory_records = [
        MemoryRecordOut(
            id=record.id,
            meeting_id=record.meeting_id,
            meeting_title=record.meeting.title if record.meeting else "",
            decision=record.decision,
            founder_decision=record.founder_decision,
            lifecycle=(
                record.lifecycle.value if isinstance(record.lifecycle, DecisionLifecycle) else str(record.lifecycle)
            ),
            success_criteria=record.success_criteria,
            review_date=record.review_date,
            actual_outcome=record.actual_outcome,
            score=round(score_decision(q, record), 3),
        )
        for record in records
    ]
    return MemoryRecallOut(
        query=q,
        records=memory_records,
        context_block=format_memory_context(records, 1500),
        total_matches=len(memory_records),
    )


@router.post("/sync", response_model=dict)
def sync_decisions(
    db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    """Backfill the register from every conclave that already has a resolution."""
    meetings = (
        db.query(BoardMeeting)
        .options(joinedload(BoardMeeting.resolution))
        .join(BoardResolution, BoardResolution.meeting_id == BoardMeeting.id)
        .filter(BoardMeeting.company_id == company.id)
        .all()
    )
    created = 0
    updated = 0
    for meeting in meetings:
        existing = (
            db.query(DecisionRecord.id)
            .filter_by(meeting_id=meeting.id)
            .first()
        )
        action = meeting.resolution.decision_status.value if meeting.resolution else ""
        sync_decision_from_meeting(db, meeting, action)
        if existing is None:
            created += 1
        else:
            updated += 1
    db.commit()
    return {"created": created, "updated": updated, "total": created + updated}


@router.post("", response_model=DecisionRecordOut, status_code=201)
def create_decision(
    payload: DecisionRecordCreate,
    db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    if payload.meeting_id is not None:
        meeting = (
            db.query(BoardMeeting)
            .options(joinedload(BoardMeeting.resolution))
            .filter_by(id=payload.meeting_id, company_id=company.id)
            .first()
        )
        if meeting is None:
            raise HTTPException(status_code=404, detail="Meeting not found.")
        existing = (
            db.query(DecisionRecord)
            .filter_by(meeting_id=meeting.id)
            .first()
        )
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail="This conclave already has a decision record; update it instead.",
            )
    values = payload.model_dump()
    values["conditions"] = merge_conditions([], payload.conditions)
    values["lifecycle"] = DecisionLifecycle(payload.lifecycle)
    values["company_id"] = company.id
    record = DecisionRecord(**values)
    db.add(record)
    db.commit()
    return _out(_get_record(db, record.id))


@router.get("/{decision_id}", response_model=DecisionRecordOut)
def get_decision(
    decision_id: int,
    db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    return _out(_require_company(_get_record(db, decision_id), company))


@router.patch("/{decision_id}", response_model=DecisionRecordOut)
def update_decision(
    decision_id: int,
    payload: DecisionRecordUpdate,
    db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    record = _require_company(_get_record(db, decision_id), company)
    values = payload.model_dump(exclude_unset=True)
    for key, value in values.items():
        if key == "conditions":
            record.conditions = merge_conditions(record.conditions or [], value)
        elif key == "lifecycle":
            if value not in LIFECYCLE_VALUES:
                raise HTTPException(status_code=422, detail=f"lifecycle must be one of {sorted(LIFECYCLE_VALUES)}")
            record.lifecycle = DecisionLifecycle(value)
        else:
            setattr(record, key, value)
    db.commit()
    return _out(_get_record(db, record.id))


@router.delete("/{decision_id}", status_code=204)
def delete_decision(
    decision_id: int,
    db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    record = db.query(DecisionRecord).filter_by(id=decision_id).first()
    record = _require_company(record, company)
    db.delete(record)
    db.commit()
    return Response(status_code=204)


@router.post("/{decision_id}/review", response_model=DecisionRecordOut)
def review_decision(
    decision_id: int,
    payload: DecisionReviewIn,
    db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    record = _require_company(_get_record(db, decision_id), company)
    now = datetime.now(timezone.utc)
    record.last_reviewed_at = now
    if payload.outcome.strip():
        record.actual_outcome = payload.outcome.strip()
    if payload.notes.strip():
        stamp = now.strftime("%Y-%m-%d")
        line = f"[{stamp} review] {payload.notes.strip()}"
        record.review_notes = "\n".join(
            part for part in (record.review_notes, line) if part
        )
    if payload.conditions is not None:
        record.conditions = merge_conditions(record.conditions or [], payload.conditions)
    if payload.new_review_date is not None:
        record.review_date = payload.new_review_date
    if payload.lifecycle:
        if payload.lifecycle not in LIFECYCLE_VALUES:
            raise HTTPException(status_code=422, detail=f"lifecycle must be one of {sorted(LIFECYCLE_VALUES)}")
        record.lifecycle = DecisionLifecycle(payload.lifecycle)
    elif payload.new_review_date is not None:
        record.lifecycle = DecisionLifecycle.open
    db.commit()
    return _out(_get_record(db, record.id))
