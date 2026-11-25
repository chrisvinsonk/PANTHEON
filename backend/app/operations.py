"""Programme 6 — Controlled operational capabilities.

Every capability produces an internal draft only. There is no external action
executor: artifacts move through draft → pending approval → founder-approved,
and an explicit instance permission is required before any future external
execution could be attempted.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from .company import company_status, ensure_company
from .models import DecisionRecord

DISCLAIMER = (
    "Generated as an internal draft. It is not delivered, sent, published or "
    "executed. External actions require explicit instance permission and "
    "founder approval."
)

CAPABILITIES = [
    {
        "kind": "project_plan",
        "label": "Project plan",
        "description": "Phase-based plan with owners, deliverables, gates and risks.",
        "permission": "workspace.artifacts.write",
        "external": False,
    },
    {
        "kind": "financial_model",
        "label": "Financial model",
        "description": "Scenario model built from the company's financial assumptions.",
        "permission": "workspace.artifacts.write",
        "external": False,
    },
    {
        "kind": "investor_document",
        "label": "Investor document",
        "description": "Investor one-pager draft assembled from approved company context.",
        "permission": "workspace.artifacts.write",
        "external": False,
    },
    {
        "kind": "task_list",
        "label": "Task list",
        "description": "Proposed tasks with owners and due dates from priorities and decrees.",
        "permission": "workspace.artifacts.write",
        "external": False,
    },
    {
        "kind": "architecture_document",
        "label": "Architecture document",
        "description": "Technical architecture draft shaped by priorities and constraints.",
        "permission": "workspace.artifacts.write",
        "external": False,
    },
    {
        "kind": "milestone_review",
        "label": "Milestone review",
        "description": "Decision deadlines, overdue work and risks in one review.",
        "permission": "workspace.artifacts.write",
        "external": False,
    },
    {
        "kind": "company_review",
        "label": "Periodic company review",
        "description": "Structured review of mission, priorities, decisions and risks.",
        "permission": "workspace.artifacts.write",
        "external": False,
    },
]

CAPABILITY_BY_KIND = {item["kind"]: item for item in CAPABILITIES}
NUMBER_RE = re.compile(r"-?\d+(?:[.,]\d+)?")


def policy(allow_external_actions: bool) -> dict:
    return {
        "approval_required": True,
        "external_actions_enabled": bool(allow_external_actions),
        "external_actions_require": (
            "Explicit instance permission and founder approval before any external effect."
        ),
        "execution_scope": "Draft artifacts only; generating one performs no external action.",
        "draft_lifecycle": "draft → pending_approval → approved or rejected",
        "audit": "Every transition is recorded on the artifact event trail.",
    }


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _number(value: str | None) -> float | None:
    if not value:
        return None
    match = NUMBER_RE.search(str(value).replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _bundle(db: Session, company):
    status = company_status(db, company)
    decisions = (
        db.query(DecisionRecord)
        .filter(DecisionRecord.company_id == company.id)
        .order_by(DecisionRecord.updated_at.desc())
        .all()
    )
    return company, status, decisions


def _active_priorities(company) -> list[dict]:
    return [
        item
        for item in (company.strategic_priorities or [])
        if str(item.get("status", "active")) != "achieved"
    ]


def _open_decisions(decisions: list[DecisionRecord]) -> list[DecisionRecord]:
    return [
        record
        for record in decisions
        if getattr(record.lifecycle, "value", record.lifecycle) in {"open", "under_review"}
    ]


def _payload(kind: str, title: str, markdown: str, sources: dict) -> dict:
    return {
        "kind": kind,
        "format": "markdown",
        "title": title,
        "markdown": markdown.strip(),
        "sources": sources,
        "disclaimer": DISCLAIMER,
        "generated_at": _now().isoformat(),
    }


def _constraints_block(company) -> list[str]:
    lines = []
    for item in company.constraints or []:
        detail = f" — {item['description']}" if item.get("description") else ""
        lines.append(f"- [{item.get('severity', 'medium')}] {item.get('label', 'Constraint')}{detail}")
    return lines or ["- No explicit constraints recorded."]


def generate_project_plan(db: Session, company, title: str, brief: str) -> dict:
    company, status, decisions = _bundle(db, company)
    priorities = _active_priorities(company)
    objective = (
        brief.strip()
        or (priorities[0]["title"] if priorities else "")
        or company.mission
        or "Clarify the next operating milestone."
    )
    phases = [
        ("Discovery", "CEO", "Reduce the largest uncertainty before committing scope."),
        ("Build", "CTO", "Deliver the smallest credible implementation."),
        ("Validate", "CSO", "Test the core claim against evidence and users."),
        ("Decide", "CFO", "Compare results with the approved budget and gates."),
    ]
    lines = [f"# {title}", "", f"> {DISCLAIMER}", "", f"**Company:** {company.name}", "", "## Objective", objective, "", "## Workstreams"]
    for index, (name, owner, intent) in enumerate(phases, start=1):
        lines.extend(
            [
                "",
                f"### {index}. {name} — owner {owner}",
                f"- Intent: {intent}",
                f"- Deliverable: {name.lower()} output reviewed at the phase gate",
                f"- Exit gate: founder accepts the evidence and releases the next phase",
            ]
        )
    lines.extend(["", "## Constraints to respect", *_constraints_block(company)])
    lines.extend(["", "## Risks to monitor"])
    risks = status.get("risks") or []
    if risks:
        for risk in risks[:6]:
            lines.append(f"- [{risk.get('severity')}] {risk.get('title')}: {risk.get('detail', '')}")
    else:
        lines.append("- No active risks recorded.")
    if priorities:
        lines.extend(["", "## Priorities served"])
        for priority in priorities:
            lines.append(f"- {priority.get('title')} ({priority.get('status', 'active')})")
    sources = {
        "company": company.name,
        "priorities": len(priorities),
        "constraints": len(company.constraints or []),
        "open_decisions": len(_open_decisions(decisions)),
    }
    return _payload("project_plan", title, "\n".join(lines), sources)


def generate_task_list(db: Session, company, title: str, brief: str) -> dict:
    company, status, decisions = _bundle(db, company)
    tasks = []
    for priority in _active_priorities(company):
        tasks.append(
            {
                "task": f"Advance priority: {priority.get('title')}",
                "owner": "CEO",
                "due": priority.get("target_date") or "not set",
                "source": "strategic priority",
            }
        )
    for record in _open_decisions(decisions)[:10]:
        tasks.append(
            {
                "task": f"Execute decree: {record.decision}",
                "owner": record.owner or "Founder",
                "due": str(record.target_date or record.review_date or "not set"),
                "source": f"decision #{record.id}",
            }
        )
    for risk in (status.get("risks") or [])[:5]:
        tasks.append(
            {
                "task": f"Resolve risk: {risk.get('title')}",
                "owner": "Founder",
                "due": "before next review",
                "source": risk.get("kind", "risk"),
            }
        )
    if not tasks:
        tasks.append(
            {
                "task": brief.strip() or "Define the next operational milestone",
                "owner": "Founder",
                "due": "not set",
                "source": "brief",
            }
        )
    lines = [f"# {title}", "", f"> {DISCLAIMER}", "", "## Proposed tasks"]
    for index, task in enumerate(tasks, start=1):
        lines.append(
            f"{index}. [ ] {task['task']} — owner: {task['owner']}, "
            f"due: {task['due']} ({task['source']})"
        )
    lines.extend(["", "## Assignment rule", "Owners are proposals only. The founder confirms every assignment."])
    sources = {"tasks": len(tasks), "company": company.name}
    return _payload("task_list", title, "\n".join(lines), sources)


def generate_financial_model(db: Session, company, title: str, brief: str) -> dict:
    company, _, decisions = _bundle(db, company)
    assumptions = company.financial_assumptions or []
    burn = next(
        (
            _number(item.get("value"))
            for item in assumptions
            if "burn" in str(item.get("label", "")).lower()
        ),
        None,
    )
    budget = next(
        (
            _number(item.get("value"))
            for item in assumptions
            if any(
                word in str(item.get("label", "")).lower()
                for word in ("budget", "pilot", "raise", "funding")
            )
        ),
        None,
    )
    committed = sum(
        _number(record.budget) or 0
        for record in decisions
        if hasattr(record, "budget")
    )
    lines = [f"# {title}", "", f"> {DISCLAIMER}", "", "## Assumptions"]
    if assumptions:
        for item in assumptions:
            value = " ".join(
                part for part in (str(item.get("value", "")), str(item.get("unit", ""))) if part
            )
            note = f" — {item['note']}" if item.get("note") else ""
            lines.append(f"- {item.get('label')}: {value}{note}")
    else:
        lines.append("- No financial assumptions recorded.")
    lines.extend(["", "## Scenarios", "| Scenario | Monthly burn | Runway |", "| --- | --- | --- |"])
    scenarios = [
        ("Base", 1.0),
        ("Conservative", 0.8),
        ("Upside", 1.25),
    ]
    for name, factor in scenarios:
        scenario_burn = burn * factor if burn else None
        runway = (
            f"{budget / scenario_burn:.1f} months"
            if budget and scenario_burn
            else "not computable"
        )
        lines.append(
            f"| {name} | {f'{scenario_burn:,.0f}' if scenario_burn else 'not set'} | {runway} |"
        )
    lines.extend(
        [
            "",
            "## Notes",
            f"- Budget baseline: {budget if budget is not None else 'not set'}",
            f"- Monthly burn baseline: {burn if burn is not None else 'not set'}",
            f"- Open decisions: {len(_open_decisions(decisions))}",
            f"- Committed budget fields on decisions: {committed:,.0f}" if committed else "- No committed decision budgets recorded.",
            "",
            "This is a planning model, not an accounting statement. The founder must review every figure.",
        ]
    )
    if brief.strip():
        lines.extend(["", "## Brief", brief.strip()])
    sources = {
        "assumptions": len(assumptions),
        "open_decisions": len(_open_decisions(decisions)),
        "company": company.name,
    }
    return _payload("financial_model", title, "\n".join(lines), sources)


def generate_investor_document(db: Session, company, title: str, brief: str) -> dict:
    company, status, _ = _bundle(db, company)
    priorities = _active_priorities(company)
    knowledge = company.approved_knowledge or []
    lines = [f"# {title}", "", f"> {DISCLAIMER}", ""]
    sections = [
        ("Problem", company.strategic_context or "To be completed by the founder."),
        ("Solution", company.mission or "To be completed by the founder."),
    ]
    for heading, body in sections:
        lines.extend([f"## {heading}", body, ""])
    lines.extend(["## Evidence", ""])
    if knowledge:
        for item in knowledge[:6]:
            lines.append(f"- {item.get('title')}: {item.get('summary', '')}")
    else:
        lines.append("- No founder-approved knowledge yet. Do not make unsupported claims.")
    lines.extend(["", "## Current priorities", ""])
    if priorities:
        for priority in priorities:
            lines.append(f"- {priority.get('title')}")
    else:
        lines.append("- No priorities recorded.")
    lines.extend(["", "## Financial frame", ""])
    for item in (company.financial_assumptions or [])[:6]:
        value = " ".join(
            part for part in (str(item.get("value", "")), str(item.get("unit", ""))) if part
        )
        lines.append(f"- {item.get('label')}: {value}")
    if not company.financial_assumptions:
        lines.append("- No financial assumptions recorded.")
    lines.extend(
        [
            "",
            "## Risks and open questions",
            "",
            *(
                [f"- [{risk.get('severity')}] {risk.get('title')}" for risk in (status.get("risks") or [])[:5]]
                or ["- No active risks recorded."]
            ),
            "",
            "## Ask",
            brief.strip() or "To be defined by the founder before any external use.",
            "",
            "## Claims discipline",
            "Every external claim must map to a verified or founder-provided evidence record.",
        ]
    )
    sources = {
        "company": company.name,
        "knowledge": len(knowledge),
        "priorities": len(priorities),
    }
    return _payload("investor_document", title, "\n".join(lines), sources)


def generate_architecture_document(db: Session, company, title: str, brief: str) -> dict:
    company, status, decisions = _bundle(db, company)
    priorities = _active_priorities(company)
    lines = [f"# {title}", "", f"> {DISCLAIMER}", ""]
    lines.extend(["## Context", company.strategic_context or company.mission or "No context recorded.", ""])
    lines.extend(["## Proposed components", ""])
    components = [
        ("Data ingestion", "Controlled import of approved datasets with provenance."),
        ("Core engine", "The smallest credible implementation of the primary capability."),
        ("Clinical workflow", "Reviewer-facing flow with explicit human sign-off."),
        ("Audit and telemetry", "Traceability for every generated output and decision."),
    ]
    for name, purpose in components:
        lines.append(f"### {name}")
        lines.append(f"- Purpose: {purpose}")
        lines.append("- Owner: CTO")
        lines.append("")
    lines.extend(["## Non-functional constraints", *_constraints_block(company), ""])
    lines.extend(["## Open technical decisions", ""])
    open_decisions = _open_decisions(decisions)
    if open_decisions:
        for record in open_decisions[:6]:
            lines.append(f"- #{record.id}: {record.decision}")
    else:
        lines.append("- No open decisions recorded.")
    if priorities:
        lines.extend(["", "## Priorities driving the design", ""])
        for priority in priorities:
            lines.append(f"- {priority.get('title')}")
    lines.extend(
        [
            "",
            "## Security posture",
            "- No patient data leaves approved environments.",
            "- Access is role-scoped and logged.",
            "- External integrations are out of scope until separately approved.",
        ]
    )
    if brief.strip():
        lines.extend(["", "## Brief", brief.strip()])
    sources = {
        "company": company.name,
        "priorities": len(priorities),
        "constraints": len(company.constraints or []),
        "risks": len(status.get("risks") or []),
    }
    return _payload("architecture_document", title, "\n".join(lines), sources)


def generate_milestone_review(db: Session, company, title: str, brief: str) -> dict:
    _, status, decisions = _bundle(db, company)
    today = date.today()
    lines = [f"# {title}", "", f"> {DISCLAIMER}", "", "## Decision milestones", ""]
    rows = decisions[:12]
    if rows:
        for record in rows:
            target = record.target_date or record.review_date
            overdue = " · OVERDUE" if target and target < today else ""
            lifecycle = getattr(record.lifecycle, "value", record.lifecycle)
            lines.append(
                f"- #{record.id} {record.decision} — owner: {record.owner or 'unassigned'}, "
                f"target: {target or 'not set'}, lifecycle: {lifecycle}{overdue}"
            )
    else:
        lines.append("- No decisions recorded.")
    lines.extend(["", "## Risks"])
    risks = status.get("risks") or []
    if risks:
        for risk in risks[:8]:
            lines.append(f"- [{risk.get('severity')}] {risk.get('title')}: {risk.get('detail', '')}")
    else:
        lines.append("- No active risks recorded.")
    lines.extend(
        [
            "",
            "## Review asks",
            "- Confirm or reset every overdue target.",
            "- Reassign any unowned milestone.",
            "- Close decisions whose outcome is already known.",
        ]
    )
    if brief.strip():
        lines.extend(["", "## Brief", brief.strip()])
    sources = {"decisions": len(decisions), "risks": len(risks)}
    return _payload("milestone_review", title, "\n".join(lines), sources)


def generate_company_review(db: Session, company, title: str, brief: str) -> dict:
    company, status, decisions = _bundle(db, company)
    counts = status.get("counts") or {}
    priorities = _active_priorities(company)
    lines = [f"# {title}", "", f"> {DISCLAIMER}", ""]
    lines.extend(["## Company", f"**{company.name}** — {company.stage or 'stage not set'}", ""])
    lines.append(company.mission or "No mission recorded.")
    lines.extend(["", "## Status", ""])
    lines.append(
        f"- Priorities active: {len(priorities)} · Open decisions: {counts.get('decisions_open', 0)} "
        f"· Reviews due: {counts.get('decisions_due', 0)}"
    )
    lines.append(
        f"- Conclaves completed: {counts.get('meetings_completed', 0)}/{counts.get('meetings_total', 0)} "
        f"· Approved knowledge: {counts.get('knowledge_approved', 0)}"
    )
    lines.extend(["", "## Priorities", ""])
    lines.extend([f"- {priority.get('title')} ({priority.get('status', 'active')})" for priority in priorities] or ["- None recorded."])
    lines.extend(["", "## Decisions", ""])
    for record in decisions[:8]:
        lifecycle = getattr(record.lifecycle, "value", record.lifecycle)
        lines.append(f"- {record.decision} — {lifecycle}, founder: {record.founder_decision or 'pending'}")
    if not decisions:
        lines.append("- None recorded.")
    lines.extend(["", "## Risks", ""])
    risks = status.get("risks") or []
    lines.extend([f"- [{risk.get('severity')}] {risk.get('title')}" for risk in risks[:6]] or ["- None detected."])
    lines.extend(
        [
            "",
            "## Recommended founder actions",
            "- Review overdue decisions and reset dates.",
            "- Confirm the next decision gate before new spend.",
            "- Approve or retire stale knowledge entries.",
        ]
    )
    if brief.strip():
        lines.extend(["", "## Brief", brief.strip()])
    sources = {"company": company.name, "decisions": len(decisions), "risks": len(risks)}
    return _payload("company_review", title, "\n".join(lines), sources)


GENERATORS = {
    "project_plan": generate_project_plan,
    "financial_model": generate_financial_model,
    "investor_document": generate_investor_document,
    "task_list": generate_task_list,
    "architecture_document": generate_architecture_document,
    "milestone_review": generate_milestone_review,
    "company_review": generate_company_review,
}


def generate(db: Session, company, kind: str, title: str, brief: str) -> dict:
    generator = GENERATORS[kind]
    return generator(db, company, title, brief)
