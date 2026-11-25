"""Programme 5 — Executive performance and governance.

Scores executive contributions on quality dimensions that cannot reward
agreement with the founder. Automatic metrics are heuristic readings of the
structured council outputs; founder feedback covers the dimensions only a human
can judge (decision usefulness and forecast accuracy).

There is deliberately no agreement/sycophancy metric anywhere in this module.
"""

from __future__ import annotations

import re
from statistics import mean
from typing import Any

from sqlalchemy.orm import Session

from .agents.contracts import (
    CLAIM_CATEGORIES,
    ExecutiveAssessment,
    ExecutiveCrossExamination,
    PositionRevision,
    parse_assessment_checkpoint,
    parse_structured_output,
)
from .models import (
    AgentContribution,
    BoardMeeting,
    ExecutiveFeedback,
    MeetingRunCheckpoint,
)

ROLES = ("CEO", "CFO", "CTO", "CSO")

METRIC_DEFINITIONS = [
    {
        "key": "evidence_discipline",
        "label": "Evidence discipline",
        "description": "Distinguishes facts from assumptions and cites evidence for factual claims.",
        "signal": "automatic",
    },
    {
        "key": "mandate_adherence",
        "label": "Mandate adherence",
        "description": "Stays within the executive's area of responsibility.",
        "signal": "automatic",
    },
    {
        "key": "challenge_quality",
        "label": "Challenge quality",
        "description": "Identifies substantive weaknesses, not cosmetic objections.",
        "signal": "automatic",
    },
    {
        "key": "position_integrity",
        "label": "Position integrity",
        "description": "Revises only when the arguments justify it, and maintains otherwise.",
        "signal": "automatic",
    },
    {
        "key": "specificity",
        "label": "Specificity",
        "description": "Recommendations are actionable, measurable and gated.",
        "signal": "automatic",
    },
    {
        "key": "forecast_accuracy",
        "label": "Forecast accuracy",
        "description": "Estimates and expectations proved reasonable, judged by the founder.",
        "signal": "founder",
    },
    {
        "key": "decision_usefulness",
        "label": "Decision usefulness",
        "description": "The contribution materially helped the founder decide, judged by the founder.",
        "signal": "founder",
    },
]

FOUNDER_METRICS = {"forecast_accuracy", "decision_usefulness"}

FEEDBACK_DIMENSIONS = tuple(metric["key"] for metric in METRIC_DEFINITIONS)

ROLE_TERMS = {
    "CEO": {
        "strategy", "strategic", "market", "customer", "customers", "growth",
        "partnership", "partnerships", "positioning", "commercial", "hiring",
        "team", "mission", "expansion", "go-to-market", "revenue model",
    },
    "CFO": {
        "budget", "runway", "burn", "cost", "costs", "capital", "cash",
        "finance", "financial", "funding", "margin", "unit economics",
        "forecast", "valuation", "spend", "pricing",
    },
    "CTO": {
        "architecture", "engineering", "technical", "technology", "security",
        "scalability", "latency", "implementation", "infrastructure", "data",
        "system", "platform", "deployment", "reliability",
    },
    "CSO": {
        "evidence", "scientific", "science", "clinical", "trial", "research",
        "validity", "study", "studies", "efficacy", "safety", "methodology",
        "dataset", "peer-reviewed", "regulatory",
    },
}

NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)?\b")


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, round(value, 1)))


def _mean(values: list[float]) -> float | None:
    return round(mean(values), 1) if values else None


def _assessment(contribution: AgentContribution) -> ExecutiveAssessment | None:
    if not (contribution.assessment or "").strip():
        return None
    try:
        assessment, _ = parse_assessment_checkpoint(contribution.assessment)
        return assessment
    except ValueError:
        return None


def _challenges(contribution: AgentContribution) -> ExecutiveCrossExamination | None:
    if not (contribution.critique or "").strip():
        return None
    try:
        return parse_structured_output(
            contribution.critique, ExecutiveCrossExamination
        )
    except ValueError:
        return None


def _revision(contribution: AgentContribution) -> PositionRevision | None:
    content = contribution.revision
    if not content:
        return None
    try:
        return parse_structured_output(content, PositionRevision)
    except ValueError:
        return None


def _all_claims(assessment: ExecutiveAssessment):
    for field in CLAIM_CATEGORIES:
        for claim in getattr(assessment, field):
            yield field, claim


def _assessment_text(assessment: ExecutiveAssessment) -> str:
    return " ".join(
        [assessment.recommendation]
        + [claim.claim for _, claim in _all_claims(assessment)]
    )


def _evidence_discipline(assessment: ExecutiveAssessment | None) -> tuple[float | None, str]:
    if assessment is None:
        return None, "No structured assessment available."
    claims = list(_all_claims(assessment))
    if not claims:
        return None, "No tagged claims were stated."
    uncertainty = sum(
        len(getattr(assessment, field))
        for field in ("assumptions", "hypotheses", "unknowns")
    )
    facts = list(assessment.supporting_facts)
    cited = sum(1 for claim in facts if claim.source_evidence_ids)
    score = 40.0
    if uncertainty:
        score += 20.0
    score += 40.0 * (cited / len(facts)) if facts else 30.0
    note = (
        f"{len(claims)} tagged claims; {uncertainty} uncertainty statements; "
        f"{cited}/{len(facts)} factual claims cite evidence."
    )
    if not uncertainty:
        note += " No assumptions, hypotheses or unknowns were disclosed."
    if facts and cited < len(facts):
        note += " Some factual claims are uncited."
    return _clamp(score), note


def _mandate_adherence(assessment: ExecutiveAssessment | None, role: str) -> tuple[float | None, str]:
    text = _assessment_text(assessment).lower() if assessment else ""
    if not text.strip():
        return None, "No assessment text available."
    own = ROLE_TERMS.get(role, set())
    other = set().union(*(terms for name, terms in ROLE_TERMS.items() if name != role))
    own_hits = sum(1 for term in own if term in text)
    other_hits = sum(1 for term in other if term in text)
    if own_hits + other_hits == 0:
        return 60.0, "No clear domain signals; treated as neutral."
    score = _clamp(100.0 * (own_hits + 2) / (own_hits + other_hits + 4))
    note = f"{own_hits} mandate signals vs {other_hits} outside-domain signals."
    return score, note


def _challenge_quality(
    challenge: ExecutiveCrossExamination | None,
    contribution: AgentContribution,
) -> tuple[float | None, str]:
    if challenge is None:
        raw = (contribution.critique or "").strip()
        if not raw:
            return None, "No challenge recorded."
        score = _clamp(25.0 + min(45.0, len(raw) / 12))
        return score, "Unstructured challenge; scored on depth only."
    scores: list[float] = []
    for item in challenge.challenges:
        score = 40.0
        if len(item.why_it_matters) >= 60:
            score += 20.0
        elif len(item.why_it_matters) >= 25:
            score += 10.0
        if len(item.challenge_question) >= 40:
            score += 20.0
        elif len(item.challenge_question) >= 20:
            score += 10.0
        if item.source_evidence_ids:
            score += 20.0
        scores.append(min(100.0, score))
    cited = sum(1 for item in challenge.challenges if item.source_evidence_ids)
    return _mean(scores), (
        f"{len(challenge.challenges)} targeted challenges; "
        f"{cited} cite evidence."
    )


def _position_integrity(revision: PositionRevision | None) -> tuple[float | None, str]:
    if revision is None:
        return 70.0, "No revision checkpoint; neutral baseline."
    if revision.position_change == "maintain":
        return 88.0, "Position maintained without an unjustified reversal."
    score = 60.0
    if revision.arguments_that_changed_my_view:
        score += 15.0
    if any(
        claim.source_evidence_ids
        for claim in revision.arguments_that_changed_my_view
    ):
        score += 15.0
    if len(revision.reason_for_change) >= 60:
        score += 10.0
    return _clamp(score), (
        f"Position {revision.position_change} with "
        f"{len(revision.arguments_that_changed_my_view)} cited argument(s)."
    )


def _specificity(assessment: ExecutiveAssessment | None) -> tuple[float | None, str]:
    if assessment is None:
        return None, "No structured assessment available."
    text = _assessment_text(assessment)
    numbers = len(set(NUMBER_RE.findall(text)))
    criteria = len(assessment.success_criteria)
    gates = len(assessment.decision_gates)
    score = 30.0 + min(30.0, criteria * 10.0) + min(20.0, gates * 10.0)
    score += min(20.0, numbers * 4.0)
    return _clamp(score), (
        f"{criteria} success criteria, {gates} decision gates, "
        f"{numbers} distinct numeric references."
    )


def _feedback_score(rating: int) -> float:
    return _clamp((rating - 1) * 25.0)


def _latest_feedback(rows: list[ExecutiveFeedback], dimension: str) -> list[ExecutiveFeedback]:
    latest: dict[str, ExecutiveFeedback] = {}
    for row in rows:
        if row.dimension != dimension:
            continue
        key = str(row.meeting_id or row.contribution_id or row.id)
        current = latest.get(key)
        if current is None or row.updated_at > current.updated_at:
            latest[key] = row
    return list(latest.values())


def _contribution_metrics(
    contribution: AgentContribution,
) -> tuple[dict[str, tuple[float | None, str]], list[tuple[float, Any]]]:
    assessment = _assessment(contribution)
    challenge = _challenges(contribution)
    revision = _revision(contribution)
    metrics = {
        "evidence_discipline": _evidence_discipline(assessment),
        "mandate_adherence": _mandate_adherence(assessment, contribution.role),
        "challenge_quality": _challenge_quality(challenge, contribution),
        "position_integrity": _position_integrity(revision),
        "specificity": _specificity(assessment),
    }
    auto_values = [
        (score, contribution.created_at)
        for score, _ in metrics.values()
        if score is not None
    ]
    return metrics, auto_values


def build_scorecards(db: Session, company_id: int | None = None) -> dict:
    contribution_query = db.query(AgentContribution).join(
        BoardMeeting, AgentContribution.meeting_id == BoardMeeting.id
    )
    feedback_query = db.query(ExecutiveFeedback)
    if company_id is not None:
        contribution_query = contribution_query.filter(
            BoardMeeting.company_id == company_id
        )
        feedback_query = feedback_query.filter(
            ExecutiveFeedback.company_id == company_id
        )
    contributions = contribution_query.order_by(
        AgentContribution.created_at.asc()
    ).all()
    feedback_rows = feedback_query.all()
    by_role: dict[str, list[AgentContribution]] = {role: [] for role in ROLES}
    for contribution in contributions:
        by_role.setdefault(contribution.role, []).append(contribution)

    scorecards = []
    for role in ROLES:
        role_contributions = by_role.get(role, [])
        role_feedback = [row for row in feedback_rows if row.role == role]
        metric_payload = []
        auto_points: list[tuple[float, Any]] = []

        per_contribution: list[dict[str, tuple[float | None, str]]] = []
        for contribution in role_contributions:
            metrics, auto_values = _contribution_metrics(contribution)
            per_contribution.append(metrics)
            auto_points.extend(auto_values)

        for definition in METRIC_DEFINITIONS:
            key = definition["key"]
            if key in FOUNDER_METRICS:
                rows = _latest_feedback(role_feedback, key)
                values = [_feedback_score(row.rating) for row in rows]
                note = (
                    f"Based on {len(rows)} founder rating(s). Not derived from "
                    "agreement with the founder."
                    if rows
                    else "No founder rating yet."
                )
                metric_payload.append(
                    {
                        **definition,
                        "score": _mean(values),
                        "sample_size": len(values),
                        "note": note,
                    }
                )
                continue
            values = [
                metrics[key][0]
                for metrics in per_contribution
                if metrics.get(key, (None, ""))[0] is not None
            ]
            notes = [
                metrics[key][1]
                for metrics in per_contribution
                if metrics.get(key, (None, ""))[0] is not None
            ]
            metric_payload.append(
                {
                    **definition,
                    "score": _mean(values),
                    "sample_size": len(values),
                    "note": notes[-1] if notes else "No structured signal yet.",
                }
            )

        available = [metric["score"] for metric in metric_payload if metric["score"] is not None]
        overall = _mean(available)
        trend = None
        if len(auto_points) >= 4:
            auto_points.sort(key=lambda item: item[1])
            midpoint = len(auto_points) // 2
            earlier = _mean([score for score, _ in auto_points[:midpoint]])
            later = _mean([score for score, _ in auto_points[midpoint:]])
            if earlier is not None and later is not None:
                trend = round(later - earlier, 1)
        last_active = max(
            [contribution.created_at for contribution in role_contributions]
            + [row.updated_at for row in role_feedback],
            default=None,
        )
        scorecards.append(
            {
                "role": role,
                "overall_score": overall,
                "trend": trend,
                "metrics": metric_payload,
                "contributions": len(role_contributions),
                "feedback_count": len(role_feedback),
                "last_active_at": last_active,
            }
        )

    return {
        "scorecards": scorecards,
        "metric_definitions": METRIC_DEFINITIONS,
        "feedback_policy": {
            "ratings": "1 (poor) to 5 (excellent)",
            "excluded_signal": "Agreement with the founder is never measured or rewarded.",
            "founder_dimensions": "Forecast accuracy and decision usefulness require founder judgement.",
            "automatic_dimensions": "The other five dimensions are heuristic readings of structured outputs.",
        },
    }


def _excerpt(text: str, limit: int = 420) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def _assessment_excerpt(contribution: AgentContribution) -> str:
    assessment = _assessment(contribution)
    if assessment is None:
        return _excerpt(contribution.assessment)
    facts = len(assessment.supporting_facts)
    assumptions = len(assessment.assumptions)
    return _excerpt(
        f"{assessment.recommendation} "
        f"({facts} supporting facts, {assumptions} assumptions, "
        f"confidence {assessment.confidence})."
    )


def _challenge_excerpt(contribution: AgentContribution) -> str:
    challenge = _challenges(contribution)
    if challenge is None:
        return _excerpt(contribution.critique)
    return _excerpt(
        " ".join(
            item.challenge_question for item in challenge.challenges
        )
    )


def _revision_excerpt(contribution: AgentContribution) -> str:
    revision = _revision(contribution)
    if revision is None:
        return ""
    return _excerpt(
        f"{revision.position_change}: {revision.reason_for_change}"
    )


def contribution_reviews(
    db: Session,
    company_id: int | None = None,
    role: str | None = None,
    meeting_id: int | None = None,
    limit: int = 25,
) -> list[dict]:
    query = (
        db.query(AgentContribution)
        .join(BoardMeeting, AgentContribution.meeting_id == BoardMeeting.id)
        .order_by(AgentContribution.created_at.desc())
    )
    if company_id is not None:
        query = query.filter(BoardMeeting.company_id == company_id)
    if role:
        query = query.filter(AgentContribution.role == role)
    if meeting_id is not None:
        query = query.filter(AgentContribution.meeting_id == meeting_id)
    contributions = query.limit(max(1, min(limit, 100))).all()
    if not contributions:
        return []

    meeting_ids = {contribution.meeting_id for contribution in contributions}
    titles = dict(
        db.query(BoardMeeting.id, BoardMeeting.title)
        .filter(BoardMeeting.id.in_(meeting_ids))
        .all()
    )
    feedback_query = db.query(ExecutiveFeedback).filter(
        ExecutiveFeedback.meeting_id.in_(meeting_ids)
    )
    if company_id is not None:
        feedback_query = feedback_query.filter(
            ExecutiveFeedback.company_id == company_id
        )
    feedback_rows = feedback_query.all()
    feedback_by_key: dict[tuple, list[ExecutiveFeedback]] = {}
    for row in feedback_rows:
        feedback_by_key.setdefault((row.meeting_id, row.role), []).append(row)

    reviews = []
    for contribution in contributions:
        rows = feedback_by_key.get((contribution.meeting_id, contribution.role), [])
        reviews.append(
            {
                "contribution_id": contribution.id,
                "role": contribution.role,
                "meeting_id": contribution.meeting_id,
                "meeting_title": titles.get(
                    contribution.meeting_id, f"Conclave #{contribution.meeting_id}"
                ),
                "created_at": contribution.created_at,
                "assessment_excerpt": _assessment_excerpt(contribution),
                "challenge_excerpt": _challenge_excerpt(contribution),
                "revision_excerpt": _revision_excerpt(contribution),
                "feedback": rows,
            }
        )
    return reviews
