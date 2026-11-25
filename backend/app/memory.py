"""Programme 3 — Decision intelligence and institutional memory.

Controlled retrieval of prior founder decrees so future council runs can reuse
decisions, rejected alternatives, failed assumptions and constraints without
dumping the whole meeting history into every prompt.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from .models import BoardMeeting, DecisionLifecycle, DecisionRecord

STOPWORDS = frozenset({
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were",
    "will", "have", "has", "had", "not", "but", "can", "could", "should",
    "would", "into", "onto", "over", "under", "when", "what", "which", "who",
    "how", "why", "our", "its", "his", "her", "their", "they", "them", "then",
    "than", "more", "most", "must", "may", "might", "shall", "also", "just",
    "about", "after", "before", "between", "during", "within", "without",
    "against", "through", "across", "board", "council", "meeting", "conclave",
})

WORD_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return [
        token
        for token in WORD_RE.findall((text or "").lower())
        if len(token) > 2 and token not in STOPWORDS
    ]


def decision_document(record: DecisionRecord) -> str:
    condition_labels = " ".join(
        str(item.get("label", "")) for item in (record.conditions or [])
    )
    return " ".join(
        part
        for part in (
            record.decision,
            record.rationale,
            record.board_recommendation,
            record.founder_notes,
            record.success_criteria,
            record.actual_outcome,
            record.review_notes,
            record.owner,
            condition_labels,
        )
        if part
    )


def _score_row(query_tokens: set[str], record: DecisionRecord) -> float:
    document = decision_document(record)
    if not document:
        return 0.0
    document_tokens = Counter(_tokens(document))
    hits = sum(1 for token in query_tokens if token in document_tokens)
    if not hits:
        return 0.0
    coverage = hits / len(query_tokens)
    rare_bonus = sum(
        0.15 for token in query_tokens
        if token in document_tokens and len(token) >= 6
    )
    return min(1.0, coverage + rare_bonus)


def score_decision(query: str, record: DecisionRecord) -> float:
    query_tokens = set(_tokens(query))
    if not query_tokens:
        return 0.0
    return _score_row(query_tokens, record)


def recall_decisions(
    db: Session,
    query: str,
    limit: int = 5,
    exclude_meeting_id: int | None = None,
    max_candidates: int = 300,
    company_id: int | None = None,
) -> list[DecisionRecord]:
    """Ranked, bounded retrieval over the decision register.

    Only decisions whose text shares meaningful tokens with the query are
    returned, ordered by coverage of the query vocabulary. The result is
    capped by ``limit`` so prompts never ingest the full history.
    """
    query_tokens = set(_tokens(query))
    if not query_tokens:
        return []
    record_query = db.query(DecisionRecord).order_by(DecisionRecord.updated_at.desc())
    if company_id is not None:
        record_query = record_query.filter(DecisionRecord.company_id == company_id)
    records = record_query.limit(max_candidates).all()
    scored: list[tuple[float, int, DecisionRecord]] = []
    for record in records:
        if exclude_meeting_id is not None and record.meeting_id == exclude_meeting_id:
            continue
        score = _score_row(query_tokens, record)
        if score <= 0:
            continue
        scored.append((score, -record.id, record))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [record for _score, _neg_id, record in scored[:max(0, limit)]]


def _condition_summary(conditions: list[dict]) -> str:
    if not conditions:
        return "none stated"
    parts = []
    for item in conditions:
        label = str(item.get("label", "")).strip()
        if not label:
            continue
        status = str(item.get("status", "pending"))
        parts.append(f"{label} ({status})" if status != "pending" else label)
    return "; ".join(parts) if parts else "none stated"


def format_memory_context(records: list[DecisionRecord | dict], max_chars: int = 1800) -> str:
    """Render recalled decisions as a bounded prompt block."""
    prefix = (
        "PRIOR DECISIONS (institutional memory — relevant past founder decrees "
        "and outcomes; treat as context, not as binding authority; verify "
        "applicability to this agenda before relying on it):\n"
    )
    if not records:
        return "No relevant prior decisions were found for this agenda."
    entries: list[str] = []
    for record in records:
        if isinstance(record, DecisionRecord):
            item = {
                "id": record.id,
                "meeting_id": record.meeting_id,
                "decision": record.decision,
                "rationale": record.rationale,
                "founder_decision": record.founder_decision,
                "lifecycle": record.lifecycle.value if record.lifecycle else record.lifecycle,
                "success_criteria": record.success_criteria,
                "review_date": (
                    record.review_date.isoformat() if record.review_date else None
                ),
                "actual_outcome": record.actual_outcome,
                "conditions": _condition_summary(record.conditions or []),
            }
        else:
            raw_conditions = record.get("conditions") or []
            if isinstance(raw_conditions, str):
                try:
                    raw_conditions = json.loads(raw_conditions)
                except (TypeError, ValueError):
                    raw_conditions = []
            item = {
                "id": record.get("id"),
                "meeting_id": record.get("meeting_id"),
                "decision": record.get("decision", ""),
                "rationale": record.get("rationale", ""),
                "founder_decision": record.get("founder_decision", ""),
                "lifecycle": record.get("lifecycle", "open"),
                "success_criteria": record.get("success_criteria", ""),
                "review_date": record.get("review_date"),
                "actual_outcome": record.get("actual_outcome", ""),
                "conditions": _condition_summary(raw_conditions),
            }
        header = (
            f"- DECISION-{item['id']} [decree {item['founder_decision'] or 'recorded'}"
            f" · {item['lifecycle'] or 'open'}"
            + (f" · review {item['review_date']}" if item.get("review_date") else "")
            + "]"
        )
        body = "\n".join(
            f"  {label}: {value}"
            for label, value in (
                ("Decision", item.get("decision", "")),
                ("Rationale", item.get("rationale", "")),
                ("Success criteria", item.get("success_criteria", "")),
                ("Outcome", item.get("actual_outcome") or "Not yet reviewed."),
                ("Conditions", item.get("conditions") or "none stated"),
            )
            if str(value).strip()
        )
        entries.append(f"{header}\n{body}")

    separator_chars = max(0, len(entries) - 1)
    per_entry_budget = max(
        180, (max_chars - len(prefix) - separator_chars) // max(1, len(entries))
    )
    trimmed = [_excerpt(entry, per_entry_budget) for entry in entries]
    return prefix + "\n".join(trimmed)


def _excerpt(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    text = text or ""
    if len(text) <= max_chars:
        return text
    marker = "\n[...trimmed to keep retrieval bounded...]\n"
    if max_chars <= len(marker):
        return text[:max_chars]
    leading = int((max_chars - len(marker)) * 0.6)
    trailing = max(0, max_chars - len(marker) - leading)
    return f"{text[:leading]}{marker}{text[-trailing:]}" if trailing else f"{text[:leading]}{marker}"


def is_review_due(record: DecisionRecord, today: date | None = None) -> bool:
    """A decision is due when its review date arrives or a tracked condition changed."""
    if record.lifecycle in {DecisionLifecycle.closed, DecisionLifecycle.superseded}:
        return False
    today = today or date.today()
    if record.review_date and record.review_date <= today:
        return True
    conditions = record.conditions or []
    if not conditions:
        return False
    last_reviewed = record.last_reviewed_at
    if last_reviewed is not None and last_reviewed.tzinfo is None:
        last_reviewed = last_reviewed.replace(tzinfo=timezone.utc)
    for condition in conditions:
        if condition.get("status") in {"met", "breached"}:
            if last_reviewed is None:
                return True
            try:
                updated = condition.get("updated_at")
                if updated:
                    parsed = datetime.fromisoformat(str(updated))
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    if parsed > last_reviewed:
                        return True
            except ValueError:
                continue
    return False


def sync_decision_from_meeting(
    db: Session,
    meeting: BoardMeeting,
    action: str | None = None,
) -> DecisionRecord:
    """Turn a founder decree into (or refresh) a structured decision record."""
    resolution = meeting.resolution
    record = (
        db.query(DecisionRecord)
        .filter_by(meeting_id=meeting.id)
        .first()
    )
    defaults = dict(
        decision=meeting.title,
        rationale=(resolution.rationale if resolution else ""),
        board_recommendation=(resolution.recommendation if resolution else ""),
        founder_notes=(resolution.founder_notes if resolution else ""),
    )
    if record is None:
        record = DecisionRecord(
            meeting_id=meeting.id,
            company_id=meeting.company_id,
            founder_decision=action or "",
            **defaults,
        )
        db.add(record)
    else:
        record.decision = record.decision or defaults["decision"]
        record.rationale = defaults["rationale"] or record.rationale
        record.board_recommendation = defaults["board_recommendation"] or record.board_recommendation
        if action:
            record.founder_decision = action
        record.founder_notes = defaults["founder_notes"] or record.founder_notes
    return record


def merge_conditions(
    existing: list[dict] | None,
    incoming: list,
) -> list[dict]:
    """Merge incoming condition items, preserving ``updated_at`` when the status did not change."""
    now = datetime.now(timezone.utc).isoformat()
    prior_by_id = {str(item.get("id", "")): item for item in existing or []}
    prior_by_label = {str(item.get("label", "")): item for item in existing or []}
    merged: list[dict] = []
    for item in incoming:
        data = item.model_dump() if hasattr(item, "model_dump") else dict(item)
        label = str(data.get("label", "")).strip()
        if not label:
            continue
        condition_id = str(data.get("id") or "") or uuid4().hex[:8]
        previous = prior_by_id.get(condition_id) or prior_by_label.get(label)
        status = str(data.get("status", "pending"))
        if (
            previous
            and str(previous.get("status", "pending")) == status
            and previous.get("updated_at")
        ):
            updated = previous["updated_at"]
        else:
            updated = data.get("updated_at") or now
        if isinstance(updated, datetime):
            updated = updated.isoformat()
        merged.append({
            "id": condition_id,
            "label": label,
            "status": status,
            "note": str(data.get("note", "")),
            "updated_at": updated,
        })
    return merged


def serialize_decision(record: DecisionRecord) -> dict:
    meeting_title = ""
    if record.meeting is not None:
        meeting_title = record.meeting.title
    conditions = []
    for item in record.conditions or []:
        if isinstance(item, dict):
            conditions.append({
                "id": str(item.get("id", "")),
                "label": str(item.get("label", "")),
                "status": str(item.get("status", "pending")),
                "note": str(item.get("note", "")),
                "updated_at": item.get("updated_at"),
            })
    return {
        "id": record.id,
        "meeting_id": record.meeting_id,
        "meeting_title": meeting_title,
        "decision": record.decision,
        "rationale": record.rationale,
        "board_recommendation": record.board_recommendation,
        "founder_decision": record.founder_decision,
        "founder_notes": record.founder_notes,
        "conditions": conditions,
        "owner": record.owner,
        "target_date": (
            record.target_date.isoformat() if record.target_date else None
        ),
        "success_criteria": record.success_criteria,
        "review_date": (
            record.review_date.isoformat() if record.review_date else None
        ),
        "actual_outcome": record.actual_outcome,
        "lifecycle": (
            record.lifecycle.value if isinstance(record.lifecycle, DecisionLifecycle) else record.lifecycle
        ),
        "last_reviewed_at": (
            record.last_reviewed_at.isoformat() if record.last_reviewed_at else None
        ),
        "review_notes": record.review_notes,
        "is_review_due": is_review_due(record),
        "created_at": (
            record.created_at.isoformat() if record.created_at else None
        ),
        "updated_at": (
            record.updated_at.isoformat() if record.updated_at else None
        ),
    }
