"""Programme 4 — Founder workspace and company context.

The Company is the workspace's context object: mission, strategic priorities,
constraints, financial assumptions and founder-approved knowledge. Every council
run receives this context so deliberations stay anchored to the company's
current strategy rather than being re-briefed from scratch each time.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.orm import Session

from .memory import is_review_due, serialize_decision
from .models import (
    AgentContribution,
    ApprovalEvent,
    BoardMeeting,
    Company,
    DecisionLifecycle,
    DecisionRecord,
    EvidenceRecord,
    MeetingRunCheckpoint,
    MeetingStatus,
)

ROLES = ("CEO", "CFO", "CTO", "CSO")
SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}

DEFAULT_COMPANY = {
    "name": "Neurotechnology Venture",
    "mission": (
        "Build scientifically rigorous neurotechnology, beginning with "
        "epilepsy-focused applications."
    ),
    "strategic_context": (
        "Early-stage venture. Initial focus is discovery and a defensible "
        "proof of concept."
    ),
    "owner": "Founder",
    "stage": "seed",
}

STARTER_PRIORITIES = [
    {
        "title": "Validate the seizure-detection MVP with two hospital partners",
        "description": (
            "Prove clinical usefulness and workflow fit before committing to a "
            "larger commercial build."
        ),
        "status": "active",
        "target_date": None,
    },
    {
        "title": "Secure dataset access and a clinical advisor",
        "description": (
            "Dataset access and clinical oversight are the gating conditions for "
            "credible validation."
        ),
        "status": "active",
        "target_date": None,
    },
    {
        "title": "Prepare the regulatory pathway briefing",
        "description": (
            "Clarify the class and evidence expectations before scaling the pilot."
        ),
        "status": "paused",
        "target_date": None,
    },
]

STARTER_CONSTRAINTS = [
    {
        "label": "Runway discipline",
        "description": "No spend beyond the approved pilot budget without a founder decree.",
        "severity": "high",
    },
    {
        "label": "Evidence-standard claims",
        "description": "Public and investor claims must match the evidence classification.",
        "severity": "high",
    },
    {
        "label": "Data privacy",
        "description": "No patient data leaves approved partner environments.",
        "severity": "high",
    },
]

STARTER_ASSUMPTIONS = [
    {
        "label": "Pilot budget",
        "value": "150000",
        "unit": "USD",
        "note": "Covers detection MVP build and the first hospital integration.",
    },
    {
        "label": "Monthly burn",
        "value": "25000",
        "unit": "USD",
        "note": "Founder-led team with contracted clinical support.",
    },
    {
        "label": "Runway",
        "value": "9",
        "unit": "months",
        "note": "Measured from the latest decreed budget baseline.",
    },
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return uuid4().hex[:8]


def touch(company: Company) -> None:
    company.updated_at = _now()


def ensure_company(
    db: Session,
    owner_user_id: str | None = None,
    *,
    name: str = DEFAULT_COMPANY["name"],
    onboarded: bool = True,
) -> Company:
    """Return a company, creating a *named* default when absent.

    This is an internal/test helper only. Request paths must never call it:
    doing so recreates a deleted company on the next read, which is exactly
    how the "blank company" kept coming back.
    """
    query = db.query(Company)
    if owner_user_id is not None:
        query = query.filter(Company.owner_user_id == owner_user_id)
    company = query.order_by(Company.id.asc()).first()
    if company is None:
        company = seed_company_profile(
            db,
            name=name,
            mission=DEFAULT_COMPANY["mission"],
            strategic_context=DEFAULT_COMPANY["strategic_context"],
            owner=DEFAULT_COMPANY["owner"],
            owner_user_id=owner_user_id,
            stage=DEFAULT_COMPANY["stage"],
            include_starters=True,
            onboarded=onboarded,
        )
    return company


def seed_company_profile(
    db: Session,
    *,
    name: str,
    mission: str = "",
    strategic_context: str = "",
    owner: str = "Founder",
    owner_user_id: str | None = None,
    stage: str = "",
    include_starters: bool = False,
    onboarded: bool = False,
) -> Company:
    """Create a company profile.

    ``include_starters`` seeds the neurotechnology starter context; new
    companies created through the switcher start with an empty profile so the
    founder can shape each venture independently.
    """
    company = Company(
        name=name,
        mission=mission,
        strategic_context=strategic_context,
        owner=owner,
        owner_user_id=owner_user_id,
        onboarded=onboarded,
        stage=stage,
        strategic_priorities=[
            {"id": _new_id(), **item} for item in (STARTER_PRIORITIES if include_starters else [])
        ],
        constraints=[
            {"id": _new_id(), **item} for item in (STARTER_CONSTRAINTS if include_starters else [])
        ],
        financial_assumptions=[
            {"id": _new_id(), **item} for item in (STARTER_ASSUMPTIONS if include_starters else [])
        ],
        approved_knowledge=[],
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


def _normalize_items(
    items: list | None,
    fields: dict[str, object],
) -> list[dict]:
    normalized: list[dict] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        record = {"id": str(item.get("id") or "")}
        for field, default in fields.items():
            value = item.get(field, default)
            record[field] = default if value is None else value
        normalized.append(record)
    return normalized


PRIORITY_FIELDS = {
    "title": "",
    "description": "",
    "status": "active",
    "target_date": None,
}
CONSTRAINT_FIELDS = {
    "label": "",
    "description": "",
    "severity": "medium",
}
ASSUMPTION_FIELDS = {
    "label": "",
    "value": "",
    "unit": "",
    "note": "",
}
KNOWLEDGE_FIELDS = {
    "title": "",
    "summary": "",
    "category": "operational",
    "source_reference": "",
    "evidence_id": None,
    "approved_at": None,
}


def serialize_company(company: Company) -> dict:
    return {
        "id": company.id,
        "name": company.name or "",
        "onboarded": bool(getattr(company, "onboarded", False)),
        "mission": company.mission or "",
        "strategic_context": company.strategic_context or "",
        "owner": company.owner or "",
        "stage": company.stage or "",
        "strategic_priorities": _normalize_items(
            company.strategic_priorities, PRIORITY_FIELDS
        ),
        "constraints": _normalize_items(company.constraints, CONSTRAINT_FIELDS),
        "financial_assumptions": _normalize_items(
            company.financial_assumptions, ASSUMPTION_FIELDS
        ),
        "approved_knowledge": _normalize_items(
            company.approved_knowledge, KNOWLEDGE_FIELDS
        ),
        "created_at": company.created_at,
        "updated_at": company.updated_at or company.created_at,
    }


# ---------------------------------------------------------------------------
# List item mutations
# ---------------------------------------------------------------------------


def _add_item(company: Company, attribute: str, item: dict) -> dict:
    record = {"id": _new_id(), **item}
    setattr(company, attribute, [*(getattr(company, attribute) or []), record])
    touch(company)
    return record


def _update_item(
    company: Company,
    attribute: str,
    item_id: str,
    changes: dict,
) -> dict | None:
    items = list(getattr(company, attribute) or [])
    for index, item in enumerate(items):
        if str(item.get("id")) != item_id:
            continue
        merged = {**item, **changes}
        items[index] = merged
        setattr(company, attribute, items)
        touch(company)
        return merged
    return None


def _delete_item(company: Company, attribute: str, item_id: str) -> bool:
    items = list(getattr(company, attribute) or [])
    kept = [item for item in items if str(item.get("id")) != item_id]
    if len(kept) == len(items):
        return False
    setattr(company, attribute, kept)
    touch(company)
    return True


def add_priority(company: Company, payload) -> dict:
    return _add_item(
        company,
        "strategic_priorities",
        payload.model_dump(mode="json"),
    )


def update_priority(company: Company, item_id: str, payload) -> dict | None:
    return _update_item(
        company,
        "strategic_priorities",
        item_id,
        payload.model_dump(exclude_unset=True, mode="json"),
    )


def delete_priority(company: Company, item_id: str) -> bool:
    return _delete_item(company, "strategic_priorities", item_id)


def add_constraint(company: Company, payload) -> dict:
    return _add_item(company, "constraints", payload.model_dump(mode="json"))


def update_constraint(company: Company, item_id: str, payload) -> dict | None:
    return _update_item(
        company,
        "constraints",
        item_id,
        payload.model_dump(exclude_unset=True, mode="json"),
    )


def delete_constraint(company: Company, item_id: str) -> bool:
    return _delete_item(company, "constraints", item_id)


def add_assumption(company: Company, payload) -> dict:
    return _add_item(
        company, "financial_assumptions", payload.model_dump(mode="json")
    )


def update_assumption(company: Company, item_id: str, payload) -> dict | None:
    return _update_item(
        company,
        "financial_assumptions",
        item_id,
        payload.model_dump(exclude_unset=True, mode="json"),
    )


def delete_assumption(company: Company, item_id: str) -> bool:
    return _delete_item(company, "financial_assumptions", item_id)


def add_knowledge(company: Company, payload) -> dict:
    data = payload.model_dump(mode="json")
    data["approved_at"] = _now().isoformat()
    return _add_item(company, "approved_knowledge", data)


def update_knowledge(company: Company, item_id: str, payload) -> dict | None:
    return _update_item(
        company,
        "approved_knowledge",
        item_id,
        payload.model_dump(exclude_unset=True, mode="json"),
    )


def delete_knowledge(company: Company, item_id: str) -> bool:
    return _delete_item(company, "approved_knowledge", item_id)


# ---------------------------------------------------------------------------
# Deliberation context
# ---------------------------------------------------------------------------


def company_context_dict(company: Company) -> dict:
    """Snapshot stored on each run and injected into council prompts.

    Deliberately excludes database timestamps so the snapshot is JSON-safe
    and only carries context the council can reason about.
    """
    data = serialize_company(company)
    return {
        "id": data["id"],
        "name": data["name"],
        "mission": data["mission"],
        "strategic_context": data["strategic_context"],
        "owner": data["owner"],
        "stage": data["stage"],
        "strategic_priorities": data["strategic_priorities"],
        "constraints": data["constraints"],
        "financial_assumptions": data["financial_assumptions"],
        "approved_knowledge": data["approved_knowledge"],
    }


def _trim(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    if max_chars <= 20:
        return text[:max_chars]
    return f"{text[: max_chars - 16]}\n…[truncated]"


def format_company_context(
    context: dict | None,
    max_chars: int = 2600,
) -> str:
    """Render the company context as a bounded prompt block.

    Returns an empty string when there is nothing meaningful to attach, so
    prompts never carry a placeholder section for an unconfigured company.
    """
    if not context:
        return ""
    name = str(context.get("name") or "").strip()
    mission = str(context.get("mission") or "").strip()
    strategic_context = str(context.get("strategic_context") or "").strip()
    owner = str(context.get("owner") or "").strip()
    stage = str(context.get("stage") or "").strip()
    priorities = [
        item for item in context.get("strategic_priorities", []) if isinstance(item, dict)
    ]
    constraints = [
        item for item in context.get("constraints", []) if isinstance(item, dict)
    ]
    assumptions = [
        item for item in context.get("financial_assumptions", []) if isinstance(item, dict)
    ]
    knowledge = [
        item for item in context.get("approved_knowledge", []) if isinstance(item, dict)
    ]
    if not any((name, mission, strategic_context, priorities, constraints, assumptions, knowledge)):
        return ""

    header_bits = [bit for bit in (stage, f"owner: {owner}" if owner else "") if bit]
    lines = [
        f"COMPANY CONTEXT — {name or 'Unnamed company'}"
        + (f" ({' · '.join(header_bits)})" if header_bits else "")
    ]
    if mission:
        lines.append(f"MISSION: {mission}")
    if strategic_context:
        lines.append(f"STRATEGIC CONTEXT: {strategic_context}")
    active_priorities = [
        item for item in priorities if str(item.get("status", "active")) != "achieved"
    ]
    if active_priorities:
        lines.append("STRATEGIC PRIORITIES:")
        for item in active_priorities:
            target = (
                f" (target {item['target_date']})"
                if item.get("target_date")
                else ""
            )
            description = (
                f" — {item['description']}" if item.get("description") else ""
            )
            lines.append(
                f"- [{item.get('status', 'active')}] {item.get('title', '')}"
                f"{target}{description}"
            )
    if constraints:
        lines.append("CONSTRAINTS:")
        for item in constraints:
            description = (
                f" — {item['description']}" if item.get("description") else ""
            )
            lines.append(
                f"- [{item.get('severity', 'medium')}] {item.get('label', '')}"
                f"{description}"
            )
    if assumptions:
        lines.append("FINANCIAL ASSUMPTIONS:")
        for item in assumptions:
            value = " ".join(
                part
                for part in (str(item.get("value", "")), str(item.get("unit", "")))
                if part
            )
            note = f" — {item['note']}" if item.get("note") else ""
            lines.append(f"- {item.get('label', '')}: {value}{note}")
    if knowledge:
        lines.append("APPROVED COMPANY KNOWLEDGE:")
        for item in knowledge:
            summary = f" — {item['summary']}" if item.get("summary") else ""
            lines.append(
                f"- {item.get('title', '')} [{item.get('category', 'general')}]"
                f"{summary}"
            )
    return _trim("\n".join(lines), max_chars)


# ---------------------------------------------------------------------------
# Command Centre aggregates
# ---------------------------------------------------------------------------


def company_status(db: Session, company: Company) -> dict:
    meetings = (
        db.query(BoardMeeting)
        .filter(BoardMeeting.company_id == company.id)
        .order_by(BoardMeeting.created_at.desc())
        .all()
    )
    decisions = (
        db.query(DecisionRecord)
        .filter(DecisionRecord.company_id == company.id)
        .order_by(DecisionRecord.updated_at.desc())
        .all()
    )
    evidence_total = (
        db.query(func.count(EvidenceRecord.id))
        .filter(EvidenceRecord.company_id == company.id)
        .scalar()
        or 0
    )
    today = date.today()

    open_lifecycles = {DecisionLifecycle.open, DecisionLifecycle.under_review}
    open_decisions = [
        record for record in decisions if record.lifecycle in open_lifecycles
    ]
    due_decisions = [record for record in decisions if is_review_due(record)]
    closed_decisions = [
        record
        for record in decisions
        if record.lifecycle in {DecisionLifecycle.closed, DecisionLifecycle.superseded}
    ]

    counts = {
        "meetings_total": len(meetings),
        "meetings_completed": sum(
            1 for meeting in meetings if meeting.status == MeetingStatus.completed
        ),
        "meetings_running": sum(
            1 for meeting in meetings if meeting.status == MeetingStatus.running
        ),
        "decisions_total": len(decisions),
        "decisions_open": len(open_decisions),
        "decisions_due": len(due_decisions),
        "decisions_closed": len(closed_decisions),
        "evidence_total": evidence_total,
        "knowledge_approved": len(company.approved_knowledge or []),
    }

    risks: dict[str, dict] = {}

    def add_risk(
        key: str,
        *,
        kind: str,
        title: str,
        detail: str,
        severity: str,
        decision_id: int | None = None,
        constraint_id: str | None = None,
    ) -> None:
        existing = risks.get(key)
        if existing and SEVERITY_RANK.get(existing["severity"], 9) <= SEVERITY_RANK.get(severity, 9):
            return
        risks[key] = {
            "kind": kind,
            "title": title,
            "detail": detail,
            "severity": severity,
            "decision_id": decision_id,
            "constraint_id": constraint_id,
        }

    for record in open_decisions:
        breached = [
            condition
            for condition in (record.conditions or [])
            if str(condition.get("status")) == "breached"
        ]
        if breached:
            labels = ", ".join(
                str(condition.get("label", "condition")) for condition in breached
            )
            add_risk(
                f"decision:{record.id}",
                kind="decision_condition_breached",
                title=record.decision,
                detail=f"Breached condition: {labels}",
                severity="high",
                decision_id=record.id,
            )
        if is_review_due(record):
            detail = (
                f"Review date {record.review_date} has passed."
                if record.review_date and record.review_date <= today
                else "A tracked condition changed since the last review."
            )
            add_risk(
                f"decision:{record.id}",
                kind="decision_review_due",
                title=record.decision,
                detail=detail,
                severity="medium",
                decision_id=record.id,
            )
        if record.target_date and record.target_date < today:
            add_risk(
                f"decision-target:{record.id}",
                kind="decision_target_overdue",
                title=record.decision,
                detail=f"Target date {record.target_date} has passed.",
                severity="medium",
                decision_id=record.id,
            )

    for constraint in company.constraints or []:
        if str(constraint.get("severity")) == "high":
            add_risk(
                f"constraint:{constraint.get('id')}",
                kind="constraint",
                title=str(constraint.get("label", "Constraint")),
                detail=str(constraint.get("description", "")),
                severity="high",
                constraint_id=str(constraint.get("id") or ""),
            )

    ordered_risks = sorted(
        risks.values(),
        key=lambda risk: SEVERITY_RANK.get(risk["severity"], 9),
    )[:12]

    return {
        "company": serialize_company(company),
        "counts": counts,
        "risks": ordered_risks,
        "recent_decisions": [
            serialize_decision(record) for record in decisions[:5]
        ],
        "recent_meetings": [
            {
                "id": meeting.id,
                "title": meeting.title,
                "status": (
                    meeting.status.value
                    if isinstance(meeting.status, MeetingStatus)
                    else str(meeting.status)
                ),
                "created_at": meeting.created_at,
            }
            for meeting in meetings[:5]
        ],
    }


# ---------------------------------------------------------------------------
# Governance and performance
# ---------------------------------------------------------------------------


def governance_snapshot(db: Session, company_id: int | None = None) -> dict:
    event_query = db.query(ApprovalEvent).order_by(ApprovalEvent.created_at.desc())
    if company_id is not None:
        meeting_ids = [
            row[0]
            for row in db.query(BoardMeeting.id)
            .filter(BoardMeeting.company_id == company_id)
            .all()
        ]
        event_query = event_query.filter(
            ApprovalEvent.meeting_id.in_(meeting_ids or [-1])
        )
    events = event_query.limit(25).all()
    meeting_ids = {event.meeting_id for event in events}
    titles = (
        dict(
            db.query(BoardMeeting.id, BoardMeeting.title)
            .filter(BoardMeeting.id.in_(meeting_ids))
            .all()
        )
        if meeting_ids
        else {}
    )
    return {
        "events": [
            {
                "id": event.id,
                "meeting_id": event.meeting_id,
                "meeting_title": titles.get(event.meeting_id, f"Conclave #{event.meeting_id}"),
                "action": event.action,
                "actor": event.actor,
                "comments": event.comments,
                "created_at": event.created_at,
            }
            for event in events
        ],
        "counts": dict(Counter(event.action for event in events)),
        "policy": {
            "decision_authority": "Founder",
            "memory_recall_limit": "3 per run, 5 via API",
            "evidence_attachment_limit": "12 per conclave",
            "review_trigger": "Review date reached or a tracked condition changed",
        },
    }


def performance_snapshot(db: Session, company_id: int | None = None) -> dict:
    decision_query = db.query(DecisionRecord)
    meeting_query = db.query(BoardMeeting)
    contribution_query = db.query(AgentContribution).join(
        BoardMeeting, AgentContribution.meeting_id == BoardMeeting.id
    )
    revision_query = db.query(MeetingRunCheckpoint).join(
        BoardMeeting, MeetingRunCheckpoint.meeting_id == BoardMeeting.id
    ).filter(MeetingRunCheckpoint.phase == "revision")
    if company_id is not None:
        decision_query = decision_query.filter(DecisionRecord.company_id == company_id)
        meeting_query = meeting_query.filter(BoardMeeting.company_id == company_id)
        contribution_query = contribution_query.filter(BoardMeeting.company_id == company_id)
        revision_query = revision_query.filter(BoardMeeting.company_id == company_id)
    decisions = decision_query.all()
    contributions = contribution_query.all()
    revisions = revision_query.all()
    meetings = meeting_query.all()

    founders = Counter(
        record.founder_decision for record in decisions if record.founder_decision
    )
    open_lifecycles = {DecisionLifecycle.open, DecisionLifecycle.under_review}

    per_role = {
        role: {
            "role": role,
            "assessments": 0,
            "challenges": 0,
            "revisions": 0,
            "models": set(),
            "last_active_at": None,
        }
        for role in ROLES
    }
    for contribution in contributions:
        bucket = per_role.setdefault(
            contribution.role,
            {
                "role": contribution.role,
                "assessments": 0,
                "challenges": 0,
                "revisions": 0,
                "models": set(),
                "last_active_at": None,
            },
        )
        if (contribution.assessment or "").strip():
            bucket["assessments"] += 1
        if (contribution.critique or "").strip():
            bucket["challenges"] += 1
        if contribution.model_name:
            bucket["models"].add(
                f"{contribution.model_provider}:{contribution.model_name}"
            )
        if (
            bucket["last_active_at"] is None
            or contribution.created_at > bucket["last_active_at"]
        ):
            bucket["last_active_at"] = contribution.created_at
    for checkpoint in revisions:
        bucket = per_role.get(checkpoint.role)
        if bucket is None:
            continue
        bucket["revisions"] += 1
        if checkpoint.updated_at and (
            bucket["last_active_at"] is None
            or checkpoint.updated_at > bucket["last_active_at"]
        ):
            bucket["last_active_at"] = checkpoint.updated_at

    executives = []
    for role in ROLES:
        bucket = per_role.get(role)
        if bucket is None:
            continue
        executives.append(
            {
                **bucket,
                "models": sorted(bucket["models"]),
            }
        )

    recent_outcomes = sorted(
        (
            record
            for record in decisions
            if (record.actual_outcome or "").strip()
            or record.lifecycle
            in {DecisionLifecycle.closed, DecisionLifecycle.superseded}
        ),
        key=lambda record: record.updated_at,
        reverse=True,
    )[:10]

    return {
        "decisions_total": len(decisions),
        "decisions_with_outcome": sum(
            1 for record in decisions if (record.actual_outcome or "").strip()
        ),
        "approved": founders.get("approved", 0),
        "rejected": founders.get("rejected", 0),
        "deferred": founders.get("deferred", 0),
        "revision_requested": founders.get("revision_requested", 0),
        "open_decisions": sum(
            1 for record in decisions if record.lifecycle in open_lifecycles
        ),
        "due_decisions": sum(1 for record in decisions if is_review_due(record)),
        "meetings_total": len(meetings),
        "meetings_completed": sum(
            1 for meeting in meetings if meeting.status == MeetingStatus.completed
        ),
        "executives": executives,
        "recent_outcomes": [
            {
                "decision_id": record.id,
                "decision": record.decision,
                "founder_decision": record.founder_decision,
                "lifecycle": (
                    record.lifecycle.value
                    if isinstance(record.lifecycle, DecisionLifecycle)
                    else str(record.lifecycle)
                ),
                "review_date": record.review_date,
                "actual_outcome": record.actual_outcome,
                "updated_at": record.updated_at,
            }
            for record in recent_outcomes
        ],
    }
