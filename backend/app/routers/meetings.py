import json
import logging
import math
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload, selectinload

from ..agents.graph import board_graph
from ..agents.contracts import (
    CLAIM_CATEGORIES,
    PositionExtraction,
    PositionRevision,
    parse_assessment_checkpoint,
    parse_structured_output,
    parse_targeted_cross_examination,
)
from ..agents.prompts import EXECUTIVE_PROFILES
from ..auth import get_current_user
from ..company import company_context_dict
from ..config import get_settings
from ..database import SessionLocal, get_db
from ..llm_config import resolve_role_llm_configs
from ..memory import recall_decisions, serialize_decision, sync_decision_from_meeting
from ..models import (
    AgentContribution,
    ApprovalEvent,
    BoardMeeting,
    BoardResolution,
    Company,
    DecisionStatus,
    EvidenceRecord,
    MeetingEvidenceLink,
    MeetingRunEvent,
    MeetingRunCheckpoint,
    MeetingStatus,
)
from ..schemas import (
    DecisionCreate,
    MeetingCreate,
    MeetingOut,
    MeetingProgressOut,
)
from ..tenancy import get_active_company

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/meetings",
    tags=["board meetings"],
    dependencies=[Depends(get_current_user)],
)

PHASE_CALLS = {
    "assessment": 4,
    "position_extraction": 0,
    "challenge": 4,
    "revision": 4,
    "synthesis": 1,
}
PROGRESS_EVENT_TYPES = (
    "run_started",
    "run_completed",
    "run_failed",
    "phase_completed",
    "agent_started",
    "agent_completed",
    "agent_failed",
    "checkpoint_reused",
)


class StaleRunAttempt(RuntimeError):
    pass


def _seconds_between(start: datetime, end: datetime) -> float:
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return max(0.0, (end - start).total_seconds())


def calculate_run_metrics(events, status: MeetingStatus, now: datetime | None = None):
    settings = get_settings()
    now = now or datetime.now(timezone.utc)
    run_started = next((event for event in events if event.event_type == "run_started"), None)
    run_ended = next(
        (event for event in events if event.event_type in {"run_completed", "run_failed"}),
        None,
    )
    elapsed_end = now if status == MeetingStatus.running or run_ended is None else run_ended.created_at
    elapsed = _seconds_between(run_started.created_at, elapsed_end) if run_started else 0.0
    starts = {}
    completed = set()
    failed = set()
    completed_phases = set()
    durations = []

    for event in events:
        key = (event.phase, event.role)
        if event.event_type == "agent_started" and event.role:
            starts[key] = event.created_at
        elif event.event_type in {"agent_completed", "checkpoint_reused"} and event.role:
            completed.add(key)
            if event.event_type == "agent_completed" and key in starts:
                durations.append(_seconds_between(starts[key], event.created_at))
        elif event.event_type == "agent_failed" and event.role:
            failed.add(key)
        elif event.event_type == "phase_completed":
            completed_phases.add(event.phase)

    average_call_seconds = max(
        1.0,
        sum(durations) / len(durations)
        if durations
        else max(1, settings.progress_initial_agent_seconds),
    )
    active = {
        key: _seconds_between(started_at, now)
        for key, started_at in starts.items()
        if key not in completed and key not in failed
    }
    completed_calls = len(completed)
    active_fraction = sum(
        min(0.9, elapsed_seconds / average_call_seconds)
        for elapsed_seconds in active.values()
    )
    if status == MeetingStatus.completed:
        progress = 100.0
        eta = None
    else:
        progress = min(99.0, (completed_calls + active_fraction) / sum(PHASE_CALLS.values()) * 100)
        eta = None
        if status == MeetingStatus.running:
            concurrency = max(1, settings.agent_concurrency)
            remaining = 0.0
            for phase, phase_call_count in PHASE_CALLS.items():
                if phase in completed_phases:
                    continue
                phase_completed = sum(1 for item in completed if item[0] == phase)
                pending_calls = phase_call_count - phase_completed
                waves = math.ceil(max(0, pending_calls) / concurrency)
                phase_estimate = waves * average_call_seconds
                phase_active_elapsed = [
                    elapsed_seconds
                    for (active_phase, _), elapsed_seconds in active.items()
                    if active_phase == phase
                ]
                if phase_active_elapsed:
                    active_elapsed = max(phase_active_elapsed)
                    projected_active_remaining = (
                        max(average_call_seconds, active_elapsed * 1.5) - active_elapsed
                    )
                    phase_estimate = (
                        max(0, waves - 1) * average_call_seconds
                        + projected_active_remaining
                    )
                remaining += max(0.0, phase_estimate)
            eta = math.ceil(remaining)

    return {
        "progress_percent": round(progress, 1),
        "elapsed_seconds": round(elapsed, 1),
        "eta_seconds": eta,
        "eta_calibrated": bool(durations),
    }


def load_meeting(db: Session, meeting_id: int, company_id: int | None = None):
    query = (
        db.query(BoardMeeting)
        .options(
            joinedload(BoardMeeting.contributions),
            joinedload(BoardMeeting.resolution),
            selectinload(BoardMeeting.run_checkpoints),
        )
        .filter(BoardMeeting.id == meeting_id)
    )
    if company_id is not None:
        query = query.filter(BoardMeeting.company_id == company_id)
    return query.first()


def add_run_event(
    db: Session,
    meeting_id: int,
    attempt: int,
    event_type: str,
    phase: str,
    message: str,
    role: str | None = None,
    checkpoint: dict | None = None,
):
    if not lock_active_run_attempt(db, meeting_id, attempt):
        db.rollback()
        raise StaleRunAttempt(
            f"Board run attempt {attempt} for meeting {meeting_id} is no longer active."
        )
    event = MeetingRunEvent(
        meeting_id=meeting_id,
        attempt=attempt,
        event_type=event_type,
        phase=phase,
        role=role,
        message=message,
    )
    db.add(event)
    if checkpoint:
        upsert_checkpoint(
            db,
            meeting_id=meeting_id,
            phase=phase,
            role=role,
            content=checkpoint["content"],
            provider=checkpoint["provider"],
            model=checkpoint["model"],
        )
    db.commit()
    return event


def is_active_run_attempt(db: Session, meeting_id: int, attempt: int) -> bool:
    status = (
        db.query(BoardMeeting.status)
        .filter(BoardMeeting.id == meeting_id)
        .scalar()
    )
    latest_attempt = (
        db.query(func.max(MeetingRunEvent.attempt))
        .filter(
            MeetingRunEvent.meeting_id == meeting_id,
            MeetingRunEvent.event_type == "run_started",
        )
        .scalar()
        or 0
    )
    return status == MeetingStatus.running and latest_attempt == attempt


def lock_active_run_attempt(db: Session, meeting_id: int, attempt: int) -> bool:
    latest_attempt = (
        db.query(func.max(MeetingRunEvent.attempt))
        .filter(
            MeetingRunEvent.meeting_id == meeting_id,
            MeetingRunEvent.event_type == "run_started",
        )
        .scalar_subquery()
    )
    updated = (
        db.query(BoardMeeting)
        .filter(
            BoardMeeting.id == meeting_id,
            BoardMeeting.status == MeetingStatus.running,
            latest_attempt == attempt,
        )
        .update(
            {BoardMeeting.status: MeetingStatus.running},
            synchronize_session=False,
        )
    )
    return updated == 1


def upsert_checkpoint(
    db: Session,
    meeting_id: int,
    phase: str,
    role: str | None,
    content: str,
    provider: str,
    model: str,
):
    if not role:
        raise ValueError("A checkpoint must identify its agent role.")
    checkpoint = (
        db.query(MeetingRunCheckpoint)
        .filter_by(meeting_id=meeting_id, phase=phase, role=role)
        .first()
    )
    if checkpoint is None:
        checkpoint = MeetingRunCheckpoint(
            meeting_id=meeting_id,
            phase=phase,
            role=role,
            content=content,
            model_provider=provider,
            model_name=model,
        )
        db.add(checkpoint)
    else:
        checkpoint.content = content
        checkpoint.model_provider = provider
        checkpoint.model_name = model
    return checkpoint


def backfill_checkpoints(db: Session, meeting_id: int):
    events = (
        db.query(MeetingRunEvent)
        .filter(
            MeetingRunEvent.meeting_id == meeting_id,
            MeetingRunEvent.event_type.in_(("agent_output", "agent_completed")),
            MeetingRunEvent.role.is_not(None),
        )
        .order_by(MeetingRunEvent.id.asc())
        .all()
    )
    streamed_content = defaultdict(list)
    completed = set()
    for event in events:
        key = (event.attempt, event.phase, event.role)
        if event.event_type == "agent_output":
            streamed_content[key].append(event.message)
        elif event.event_type == "agent_completed":
            completed.add(key)

    latest_completed = {}
    for attempt, phase, role in completed:
        key = (phase, role)
        if key not in latest_completed or attempt > latest_completed[key]:
            latest_completed[key] = attempt
    existing = {
        (checkpoint.phase, checkpoint.role)
        for checkpoint in db.query(MeetingRunCheckpoint)
        .filter(MeetingRunCheckpoint.meeting_id == meeting_id)
        .all()
    }
    for (phase, role), attempt in latest_completed.items():
        if (phase, role) in existing:
            continue
        content = "".join(streamed_content[(attempt, phase, role)]).strip()
        if content:
            upsert_checkpoint(
                db,
                meeting_id=meeting_id,
                phase=phase,
                role=role,
                content=content,
                provider="unknown",
                model="",
            )
            existing.add((phase, role))

    for contribution in (
        db.query(AgentContribution)
        .filter(AgentContribution.meeting_id == meeting_id)
        .all()
    ):
        content = contribution.assessment if contribution.phase == "assessment" else contribution.critique
        if content and (contribution.phase, contribution.role) not in existing:
            upsert_checkpoint(
                db,
                meeting_id=meeting_id,
                phase=contribution.phase,
                role=contribution.role,
                content=content,
                provider=contribution.model_provider,
                model=contribution.model_name,
            )
            existing.add((contribution.phase, contribution.role))

    resolution = (
        db.query(BoardResolution)
        .filter(BoardResolution.meeting_id == meeting_id)
        .first()
    )
    if resolution and ("synthesis", "BOARD") not in existing:
        upsert_checkpoint(
            db,
            meeting_id=meeting_id,
            phase="synthesis",
            role="BOARD",
            content=resolution.recommendation,
            provider="unknown",
            model="",
        )


def recover_interrupted_runs(db: Session):
    running_meetings = (
        db.query(BoardMeeting)
        .filter(BoardMeeting.status == MeetingStatus.running)
        .all()
    )
    for meeting in running_meetings:
        backfill_checkpoints(db, meeting.id)
        attempt = (
            db.query(func.max(MeetingRunEvent.attempt))
            .filter(MeetingRunEvent.meeting_id == meeting.id)
            .scalar()
            or 1
        )
        meeting.status = MeetingStatus.failed
        meeting.completed_at = None
        db.add(
            MeetingRunEvent(
                meeting_id=meeting.id,
                attempt=attempt,
                event_type="run_failed",
                phase="interrupted",
                message=(
                    "The API restarted before this run completed. Retry will reuse "
                    "all completed agent checkpoints."
                ),
            )
        )
    if running_meetings:
        db.commit()
        logger.warning("Marked %s interrupted board run(s) retryable.", len(running_meetings))


def _evidence_snapshot_entry(record: EvidenceRecord) -> dict:
    return {
        "id": record.id,
        "claim": record.claim,
        "category": record.category,
        "classification": record.classification,
        "source_provider": record.source_provider,
        "source_title": record.source_title,
        "source_reference": record.source_reference,
        "source_url": record.source_url,
        "publication_date": (
            record.publication_date.isoformat() if record.publication_date else None
        ),
        "retrieved_at": record.retrieved_at.isoformat() if record.retrieved_at else None,
        "evidence_quality": record.evidence_quality,
        "limitations": record.limitations,
        "source_excerpt": record.source_excerpt,
        "relying_executives": record.relying_executives or [],
        "challenged": record.challenged,
        "challenged_by": record.challenged_by or [],
        "disputed": record.disputed,
        "disputed_by": record.disputed_by or [],
        "dispute_notes": record.dispute_notes,
    }


def _apply_evidence_outcomes(
    db: Session,
    meeting_id: int,
    evidence_register: list[dict],
    result: dict,
) -> None:
    usage_by_evidence: dict[int, set[str]] = defaultdict(set)
    challenge_by_evidence: dict[int, set[str]] = defaultdict(set)
    disputes_by_evidence: dict[int, list[str]] = defaultdict(list)

    for role, content in result.get("assessments", {}).items():
        candidate = content.strip()
        if not (candidate.startswith("{") or candidate.startswith("```json")):
            continue
        assessment, _ = parse_assessment_checkpoint(content)
        for category in CLAIM_CATEGORIES:
            for claim in getattr(assessment, category):
                for evidence_id in claim.source_evidence_ids:
                    usage_by_evidence[evidence_id].add(role)
    for role, content in result.get("revisions", {}).items():
        candidate = content.strip()
        if not (candidate.startswith("{") or candidate.startswith("```json")):
            continue
        revision = parse_structured_output(content, PositionRevision)
        for claim in (
            revision.arguments_that_changed_my_view
            + revision.remaining_disagreements
        ):
            for evidence_id in claim.source_evidence_ids:
                usage_by_evidence[evidence_id].add(role)

    extraction_content = result.get("position_extraction", "")
    if extraction_content:
        extraction = parse_structured_output(extraction_content, PositionExtraction)
        available_ids = {
            int(item["id"]) for item in evidence_register
        }
        for role, content in result.get("critiques", {}).items():
            examination = parse_targeted_cross_examination(
                content,
                role,
                extraction,
                EXECUTIVE_PROFILES[role].challenge_categories,
                available_evidence_ids=available_ids,
            )
            if examination is None:
                continue
            for challenge in examination.challenges:
                for evidence_id in challenge.source_evidence_ids:
                    challenge_by_evidence[evidence_id].add(role)
                for evidence_id in challenge.disputed_evidence_ids:
                    disputes_by_evidence[evidence_id].append(
                        f"{role}: {challenge.challenge_question} "
                        f"({challenge.why_it_matters})"
                    )

    affected_ids = (
        set(usage_by_evidence)
        | set(challenge_by_evidence)
        | set(disputes_by_evidence)
    )
    if not affected_ids:
        return
    records = {
        record.id: record
        for record in db.query(EvidenceRecord)
        .filter(EvidenceRecord.id.in_(affected_ids))
        .all()
    }
    for evidence_id, record in records.items():
        record.relying_executives = sorted(
            set(record.relying_executives or []) | usage_by_evidence[evidence_id]
        )
        challenge_roles = challenge_by_evidence[evidence_id]
        if challenge_roles:
            record.challenged = True
            record.challenged_by = sorted(
                set(record.challenged_by or []) | challenge_roles
            )
        dispute_lines = list(dict.fromkeys(disputes_by_evidence[evidence_id]))
        if dispute_lines:
            record.disputed = True
            record.disputed_by = sorted(
                set(record.disputed_by or []) | challenge_by_evidence[evidence_id]
            )
            prior_lines = record.dispute_notes.splitlines() if record.dispute_notes else []
            record.dispute_notes = "\n".join(
                dict.fromkeys(prior_lines + dispute_lines)
            )

    snapshot = (
        db.query(MeetingRunCheckpoint)
        .filter_by(
            meeting_id=meeting_id,
            phase="evidence_snapshot",
            role="BOARD",
        )
        .first()
    )
    if snapshot is not None:
        snapshot_records = json.loads(snapshot.content)
        outcome_fields = (
            "relying_executives",
            "challenged",
            "challenged_by",
            "disputed",
            "disputed_by",
            "dispute_notes",
        )
        for item in snapshot_records:
            record = records.get(int(item["id"]))
            if record is not None:
                current = _evidence_snapshot_entry(record)
                item.update({field: current[field] for field in outcome_fields})
        snapshot.content = json.dumps(snapshot_records, ensure_ascii=True)


def _apply_checkpointed_evidence_outcomes(
    db: Session,
    meeting_id: int,
    evidence_register: list[dict],
) -> None:
    state = {
        "assessments": {},
        "critiques": {},
        "revisions": {},
    }
    for checkpoint in (
        db.query(MeetingRunCheckpoint)
        .filter_by(meeting_id=meeting_id)
        .all()
    ):
        if checkpoint.phase == "assessment":
            state["assessments"][checkpoint.role] = checkpoint.content
        elif checkpoint.phase == "challenge":
            state["critiques"][checkpoint.role] = checkpoint.content
        elif checkpoint.phase == "revision":
            state["revisions"][checkpoint.role] = checkpoint.content
        elif checkpoint.phase == "position_extraction" and checkpoint.role == "BOARD":
            state["position_extraction"] = checkpoint.content
    _apply_evidence_outcomes(db, meeting_id, evidence_register, state)


@router.get("", response_model=list[MeetingOut], tags=["board meetings"])
def list_meetings(
    db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    return (
        db.query(BoardMeeting)
        .options(
            joinedload(BoardMeeting.contributions),
            joinedload(BoardMeeting.resolution),
            selectinload(BoardMeeting.run_checkpoints),
        )
        .filter(BoardMeeting.company_id == company.id)
        .order_by(BoardMeeting.created_at.desc())
        .limit(50)
        .all()
    )


@router.post("", response_model=MeetingOut, tags=["board meetings"])
def create_meeting(
    payload: MeetingCreate,
    db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    if len(set(payload.evidence_ids)) != len(payload.evidence_ids):
        raise HTTPException(status_code=422, detail="Evidence IDs must be unique.")
    records = (
        db.query(EvidenceRecord)
        .filter(
            EvidenceRecord.id.in_(payload.evidence_ids),
            EvidenceRecord.company_id == company.id,
        )
        .all()
        if payload.evidence_ids
        else []
    )
    if len(records) != len(payload.evidence_ids):
        raise HTTPException(status_code=404, detail="One or more evidence records were not found.")
    meeting = BoardMeeting(
        company_id=company.id,
        title=payload.title,
        agenda=payload.agenda,
        founder_context=payload.founder_context,
        include_memory=payload.include_memory,
    )
    db.add(meeting)
    db.flush()
    db.add_all(
        MeetingEvidenceLink(meeting_id=meeting.id, evidence_id=record.id)
        for record in records
    )
    db.commit()
    db.refresh(meeting)
    return load_meeting(db, meeting.id)


@router.get("/{meeting_id}", response_model=MeetingOut, tags=["board meetings"])
def get_meeting(
    meeting_id: int,
    db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    meeting = load_meeting(db, meeting_id, company.id)
    if not meeting:
        raise HTTPException(404, "Meeting not found")
    return meeting


@router.get("/{meeting_id}/progress", response_model=MeetingProgressOut)
def get_meeting_progress(
    meeting_id: int,
    after_id: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    meeting = load_meeting(db, meeting_id, company.id)
    if not meeting:
        raise HTTPException(404, "Meeting not found")
    events = (
        db.query(MeetingRunEvent)
        .filter(
            MeetingRunEvent.meeting_id == meeting_id,
            MeetingRunEvent.id > after_id,
        )
        .order_by(MeetingRunEvent.id.asc())
        .limit(100)
        .all()
    )
    latest_attempt = (
        db.query(func.max(MeetingRunEvent.attempt))
        .filter(MeetingRunEvent.meeting_id == meeting_id)
        .scalar()
        or 0
    )
    checkpoint_keys = {
        (event.phase, event.role)
        for event in events
        if event.event_type in {"checkpoint_saved", "checkpoint_reused"} and event.role
    }
    checkpoint_query = db.query(MeetingRunCheckpoint).filter(
        MeetingRunCheckpoint.meeting_id == meeting_id,
        MeetingRunCheckpoint.phase != "evidence_snapshot",
        MeetingRunCheckpoint.phase != "institutional_memory",
        MeetingRunCheckpoint.phase != "company_context",
    )
    evidence_snapshot = (
        db.query(MeetingRunCheckpoint)
        .filter_by(
            meeting_id=meeting_id,
            phase="evidence_snapshot",
            role="BOARD",
        )
        .first()
    )
    evidence_register = (
        json.loads(evidence_snapshot.content)
        if evidence_snapshot is not None
        else []
    )
    memory_snapshot = (
        db.query(MeetingRunCheckpoint)
        .filter_by(
            meeting_id=meeting_id,
            phase="institutional_memory",
            role="BOARD",
        )
        .first()
    )
    institutional_memory = (
        json.loads(memory_snapshot.content)
        if memory_snapshot is not None
        else []
    )
    company_snapshot = (
        db.query(MeetingRunCheckpoint)
        .filter_by(
            meeting_id=meeting_id,
            phase="company_context",
            role="BOARD",
        )
        .first()
    )
    try:
        company_context = (
            json.loads(company_snapshot.content)
            if company_snapshot is not None
            else {}
        )
    except json.JSONDecodeError:
        company_context = {}
    if after_id == 0:
        checkpoints = checkpoint_query.order_by(MeetingRunCheckpoint.id.asc()).all()
    elif checkpoint_keys:
        checkpoints = (
            checkpoint_query.filter(
                or_(*[
                    and_(
                        MeetingRunCheckpoint.phase == phase,
                        MeetingRunCheckpoint.role == role,
                    )
                    for phase, role in checkpoint_keys
                ])
            )
            .order_by(MeetingRunCheckpoint.id.asc())
            .all()
        )
    else:
        checkpoints = []
    estimate_events = (
        db.query(MeetingRunEvent)
        .filter(
            MeetingRunEvent.meeting_id == meeting_id,
            MeetingRunEvent.attempt == latest_attempt,
            MeetingRunEvent.event_type.in_(PROGRESS_EVENT_TYPES),
        )
        .order_by(MeetingRunEvent.id.asc())
        .all()
    )
    return {
        "meeting": meeting,
        "events": events,
        "checkpoints": checkpoints,
        "evidence_register": evidence_register,
        "institutional_memory": institutional_memory,
        "company_context": company_context,
        "has_more": len(events) == 100,
        **calculate_run_metrics(estimate_events, meeting.status),
    }


async def run_meeting_in_background(meeting_id: int, attempt: int):
    initial_db = SessionLocal()
    try:
        meeting = initial_db.query(BoardMeeting).filter_by(id=meeting_id).first()
        if not meeting:
            logger.error("Cannot start board run for missing meeting %s", meeting_id)
            return
        if not is_active_run_attempt(initial_db, meeting_id, attempt):
            logger.info(
                "Skipping stale board run attempt %s for meeting %s.",
                attempt,
                meeting_id,
            )
            return
        meeting_input = {
            "title": meeting.title,
            "agenda": meeting.agenda,
            "founder_context": meeting.founder_context,
        }
        snapshot_checkpoint = (
            initial_db.query(MeetingRunCheckpoint)
            .filter_by(
                meeting_id=meeting_id,
                phase="evidence_snapshot",
                role="BOARD",
            )
            .first()
        )
        if snapshot_checkpoint is not None:
            try:
                evidence_register = json.loads(snapshot_checkpoint.content)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"Meeting {meeting_id} has a malformed evidence snapshot checkpoint."
                ) from exc
        else:
            evidence_links = (
                initial_db.query(MeetingEvidenceLink)
                .options(joinedload(MeetingEvidenceLink.evidence))
                .filter_by(meeting_id=meeting_id)
                .order_by(MeetingEvidenceLink.id.asc())
                .all()
            )
            evidence_register = [
                _evidence_snapshot_entry(link.evidence)
                for link in evidence_links
            ]
            snapshot_checkpoint = MeetingRunCheckpoint(
                meeting_id=meeting_id,
                phase="evidence_snapshot",
                role="BOARD",
                content=json.dumps(evidence_register, ensure_ascii=True),
                model_provider="system",
                model_name="evidence-register-snapshot-v1",
            )
            initial_db.add(snapshot_checkpoint)
            initial_db.commit()
        meeting_input["evidence_register"] = evidence_register
        memory_checkpoint = (
            initial_db.query(MeetingRunCheckpoint)
            .filter_by(
                meeting_id=meeting_id,
                phase="institutional_memory",
                role="BOARD",
            )
            .first()
        )
        if memory_checkpoint is not None:
            try:
                institutional_memory = json.loads(memory_checkpoint.content)
            except json.JSONDecodeError:
                institutional_memory = []
        else:
            institutional_memory = []
            if meeting.include_memory:
                institutional_memory = recall_decisions(
                    initial_db,
                    f"{meeting.title}\n{meeting.agenda}\n{meeting.founder_context}",
                    limit=3,
                    exclude_meeting_id=meeting_id,
                    company_id=meeting.company_id,
                )
                initial_db.add(
                    MeetingRunCheckpoint(
                        meeting_id=meeting_id,
                        phase="institutional_memory",
                        role="BOARD",
                        content=json.dumps(
                            [serialize_decision(record) for record in institutional_memory],
                            ensure_ascii=True,
                        ),
                        model_provider="system",
                        model_name="institutional-memory-snapshot-v1",
                    )
                )
            initial_db.commit()
        meeting_input["institutional_memory"] = institutional_memory
        company_snapshot = (
            initial_db.query(MeetingRunCheckpoint)
            .filter_by(
                meeting_id=meeting_id,
                phase="company_context",
                role="BOARD",
            )
            .first()
        )
        if company_snapshot is not None:
            try:
                company_context = json.loads(company_snapshot.content)
            except json.JSONDecodeError:
                company_context = {}
        else:
            meeting_company = (
                initial_db.get(Company, meeting.company_id)
                if meeting.company_id is not None
                else None
            )
            company_context = (
                company_context_dict(meeting_company)
                if meeting_company is not None
                else {}
            )
            initial_db.add(
                MeetingRunCheckpoint(
                    meeting_id=meeting_id,
                    phase="company_context",
                    role="BOARD",
                    content=json.dumps(company_context, ensure_ascii=True),
                    model_provider="system",
                    model_name="company-context-snapshot-v1",
                )
            )
            initial_db.commit()
        meeting_input["company_context"] = company_context
        checkpoints = (
            initial_db.query(MeetingRunCheckpoint)
            .filter(MeetingRunCheckpoint.meeting_id == meeting_id)
            .all()
        )
        assessments = {}
        position_extraction = None
        critiques = {}
        revisions = {}
        provider_metadata = {}
        for checkpoint in checkpoints:
            if checkpoint.phase == "assessment":
                assessments[checkpoint.role] = checkpoint.content
            elif checkpoint.phase == "position_extraction" and checkpoint.role == "BOARD":
                position_extraction = checkpoint.content
            elif checkpoint.phase == "challenge":
                critiques[checkpoint.role] = checkpoint.content
            elif checkpoint.phase == "revision":
                revisions[checkpoint.role] = checkpoint.content
            elif checkpoint.phase == "synthesis" and checkpoint.role == "BOARD":
                meeting_input["recommendation"] = checkpoint.content
            if checkpoint.phase not in {"position_extraction", "evidence_snapshot", "institutional_memory", "company_context"}:
                provider_metadata[checkpoint.role] = {
                    "provider": checkpoint.model_provider,
                    "model": checkpoint.model_name,
                }
        meeting_input.update({
            "assessments": assessments,
            "critiques": critiques,
            "revisions": revisions,
            "provider_metadata": provider_metadata,
        })
        if position_extraction:
            meeting_input["position_extraction"] = position_extraction
    finally:
        initial_db.close()

    async def report_progress(event: dict):
        event_db = SessionLocal()
        try:
            add_run_event(
                event_db,
                meeting_id=meeting_id,
                attempt=attempt,
                event_type=event["event_type"],
                phase=event["phase"],
                role=event.get("role"),
                message=event["message"],
                checkpoint=event if event["event_type"] == "checkpoint_saved" else None,
            )
            if event["event_type"] in {"checkpoint_saved", "checkpoint_reused"}:
                _apply_checkpointed_evidence_outcomes(
                    event_db,
                    meeting_id,
                    meeting_input.get("evidence_register", []),
                )
                event_db.commit()
        finally:
            event_db.close()

    try:
        config_db = SessionLocal()
        try:
            llm_configs = resolve_role_llm_configs(config_db)
        finally:
            config_db.close()
        result = await board_graph.ainvoke(
            meeting_input,
            config={
                "configurable": {
                    "progress_callback": report_progress,
                    "llm_configs": llm_configs,
                }
            },
        )
        db = SessionLocal()
        try:
            meeting = db.query(BoardMeeting).filter_by(id=meeting_id).first()
            if not meeting:
                raise RuntimeError(f"Meeting {meeting_id} no longer exists.")
            if not lock_active_run_attempt(db, meeting_id, attempt):
                logger.info(
                    "Discarding completion from stale board run attempt %s for meeting %s.",
                    attempt,
                    meeting_id,
                )
                return
            _apply_evidence_outcomes(
                db,
                meeting_id,
                meeting_input.get("evidence_register", []),
                result,
            )
            for role in ("CEO", "CFO", "CTO", "CSO"):
                metadata = result.get("provider_metadata", {}).get(role, {})
                for phase, content in (
                    ("assessment", result.get("assessments", {}).get(role, "")),
                    ("challenge", result.get("critiques", {}).get(role, "")),
                ):
                    contribution = (
                        db.query(AgentContribution)
                        .filter_by(meeting_id=meeting_id, role=role, phase=phase)
                        .first()
                    )
                    if contribution is None:
                        contribution = AgentContribution(
                            meeting_id=meeting_id,
                            role=role,
                            phase=phase,
                        )
                        db.add(contribution)
                    if phase == "assessment":
                        contribution.assessment = content
                    else:
                        contribution.critique = content
                    contribution.model_provider = metadata.get("provider", "unknown")
                    contribution.model_name = metadata.get("model", "")
            resolution = (
                db.query(BoardResolution)
                .filter_by(meeting_id=meeting_id)
                .first()
            )
            if resolution is None:
                resolution = BoardResolution(
                    meeting_id=meeting_id,
                    recommendation=result["recommendation"],
                    decision_status=DecisionStatus.pending,
                )
                db.add(resolution)
            resolution.recommendation = result["recommendation"]
            resolution.rationale = result.get("rationale", "")
            resolution.dissent_and_open_questions = result.get("dissent", "")
            meeting.status = MeetingStatus.completed
            meeting.completed_at = datetime.now(timezone.utc)
            db.add(
                MeetingRunEvent(
                    meeting_id=meeting_id,
                    attempt=attempt,
                    event_type="run_completed",
                    phase="complete",
                    message="Board deliberation completed successfully.",
                )
            )
            db.commit()
        finally:
            db.close()
    except StaleRunAttempt:
        logger.info(
            "Stopping stale board run attempt %s for meeting %s.",
            attempt,
            meeting_id,
        )
    except Exception as exc:
        failure_db = SessionLocal()
        try:
            meeting = failure_db.query(BoardMeeting).filter_by(id=meeting_id).first()
            if meeting and lock_active_run_attempt(failure_db, meeting_id, attempt):
                logger.exception("Board deliberation failed for meeting %s", meeting_id)
                meeting.status = MeetingStatus.failed
                failure_db.add(
                    MeetingRunEvent(
                        meeting_id=meeting_id,
                        attempt=attempt,
                        event_type="run_failed",
                        phase="failed",
                        message=f"Board deliberation failed: {exc}",
                    )
                )
                failure_db.commit()
            elif meeting:
                logger.info(
                    "Ignoring failure from stale board run attempt %s for meeting %s: %s",
                    attempt,
                    meeting_id,
                    exc,
                )
        finally:
            failure_db.close()


@router.post(
    "/{meeting_id}/run",
    response_model=MeetingOut,
    status_code=202,
    tags=["board meetings"],
)
async def run_meeting(
    meeting_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    updated = (
        db.query(BoardMeeting)
        .filter(
            BoardMeeting.id == meeting_id,
            BoardMeeting.company_id == company.id,
            BoardMeeting.status.in_([MeetingStatus.draft, MeetingStatus.failed]),
        )
        .update(
            {
                BoardMeeting.status: MeetingStatus.running,
                BoardMeeting.completed_at: None,
            },
            synchronize_session=False,
        )
    )
    if not updated:
        meeting = (
            db.query(BoardMeeting)
            .filter_by(id=meeting_id, company_id=company.id)
            .first()
        )
        if not meeting:
            raise HTTPException(404, "Meeting not found")
        if meeting.status == MeetingStatus.running:
            raise HTTPException(409, "Meeting is already running")
        raise HTTPException(409, "Meeting has already completed")

    backfill_checkpoints(db, meeting_id)
    previous_attempt = (
        db.query(func.max(MeetingRunEvent.attempt))
        .filter(MeetingRunEvent.meeting_id == meeting_id)
        .scalar()
        or 0
    )
    attempt = previous_attempt + 1
    db.add(
        MeetingRunEvent(
            meeting_id=meeting_id,
            attempt=attempt,
            event_type="run_started",
            phase="setup",
            message=f"Board deliberation started (attempt {attempt}).",
        )
    )
    db.commit()
    background_tasks.add_task(run_meeting_in_background, meeting_id, attempt)
    return load_meeting(db, meeting_id)


@router.post("/{meeting_id}/decision", response_model=MeetingOut, tags=["board meetings"])
def record_decision(
    meeting_id: int,
    payload: DecisionCreate,
    db: Session = Depends(get_db),
    company: Company = Depends(get_active_company),
):
    meeting = load_meeting(db, meeting_id, company.id)
    if not meeting:
        raise HTTPException(404, "Meeting not found")
    if not meeting.resolution:
        raise HTTPException(409, "Run the board meeting before recording a decision")
    mapping = {
        "approve": DecisionStatus.approved,
        "reject": DecisionStatus.rejected,
        "revise": DecisionStatus.revision_requested,
        "defer": DecisionStatus.deferred,
    }
    meeting.resolution.decision_status = mapping[payload.action]
    meeting.resolution.founder_notes = payload.comments
    meeting.resolution.decided_at = datetime.now(timezone.utc)
    sync_decision_from_meeting(db, meeting, mapping[payload.action].value)
    db.add(
        ApprovalEvent(
            meeting_id=meeting.id,
            action=payload.action,
            actor=payload.actor,
            comments=payload.comments,
        )
    )
    db.commit()
    return load_meeting(db, meeting_id)
