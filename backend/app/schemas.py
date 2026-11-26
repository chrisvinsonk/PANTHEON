from datetime import date, datetime
from typing import Any, Literal
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from .models import MeetingStatus, DecisionStatus

EvidenceCategory = Literal[
    "scientific",
    "technical",
    "financial",
    "commercial",
    "regulatory",
    "operational",
]
EvidenceClassification = Literal[
    "verified",
    "founder-provided",
    "assumption",
    "estimate",
    "hypothesis",
    "unknown",
]
EvidenceQuality = Literal["unassessed", "low", "moderate", "high"]
ExecutiveRoleName = Literal["CEO", "CFO", "CTO", "CSO"]


class EvidenceSnapshotOut(BaseModel):
    id: int
    claim: str
    category: EvidenceCategory
    classification: EvidenceClassification
    source_provider: Literal["manual", "pubmed", "clinicaltrials", "openfda", "tavily"]
    source_title: str
    source_reference: str
    source_url: str
    publication_date: date | None
    retrieved_at: datetime | None
    evidence_quality: EvidenceQuality
    limitations: str
    source_excerpt: str
    relying_executives: list[ExecutiveRoleName]
    challenged: bool
    challenged_by: list[ExecutiveRoleName] = Field(default_factory=list)
    disputed: bool
    disputed_by: list[ExecutiveRoleName] = Field(default_factory=list)
    dispute_notes: str


class MeetingCreate(BaseModel):
    title: str = Field(min_length=3, max_length=240)
    agenda: str = Field(min_length=10)
    founder_context: str = ""
    evidence_ids: list[int] = Field(default_factory=list, max_length=12)
    include_memory: bool = True

class ContributionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    role: str
    phase: str
    assessment: str
    critique: str
    revision: str | None = None
    model_provider: str
    model_name: str

class ResolutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    recommendation: str
    rationale: str
    dissent_and_open_questions: str
    decision_status: DecisionStatus
    founder_notes: str

class MeetingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    agenda: str
    founder_context: str
    include_memory: bool = True
    status: MeetingStatus
    created_at: datetime
    completed_at: datetime | None
    contributions: list[ContributionOut] = []
    resolution: ResolutionOut | None = None

class MeetingRunEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    attempt: int
    event_type: str
    phase: str
    role: str | None
    message: str
    created_at: datetime

class MeetingRunCheckpointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    phase: str
    role: str
    content: str
    model_provider: str
    model_name: str
    updated_at: datetime

class MeetingProgressOut(BaseModel):
    meeting: MeetingOut
    events: list[MeetingRunEventOut]
    checkpoints: list[MeetingRunCheckpointOut] = []
    evidence_register: list[EvidenceSnapshotOut] = Field(default_factory=list)
    institutional_memory: list[dict] = Field(default_factory=list)
    company_context: dict = Field(default_factory=dict)
    has_more: bool = False
    progress_percent: float = 0
    elapsed_seconds: float = 0
    eta_seconds: int | None = None
    eta_calibrated: bool = False

class DecisionCreate(BaseModel):
    action: str = Field(pattern="^(approve|reject|revise|defer)$")
    comments: str = ""
    actor: str = "Founder"

class ExecutiveOut(BaseModel):
    role: str
    title: str
    mandate: str

class LLMSourceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    provider: Literal[
        "lm_studio",
        "ollama",
        "openai",
        "anthropic",
        "google_gemini",
        "openrouter",
        "groq",
        "together",
        "fireworks",
        "mistral",
        "deepseek",
        "xai",
        "cerebras",
        "custom",
    ]
    base_url: str | None = Field(default=None, max_length=500)
    api_key: SecretStr | None = None

class LLMSourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    base_url: str | None = Field(default=None, max_length=500)
    api_key: SecretStr | None = None
    clear_api_key: bool = False

class LLMSourceOut(BaseModel):
    id: int
    name: str
    provider: str
    base_url: str
    api_key_configured: bool

class AgentLLMRouteSet(BaseModel):
    source_id: int = Field(gt=0)
    model_name: str = Field(min_length=1, max_length=160)

class AgentLLMRoutesBulkSet(BaseModel):
    source_id: int = Field(gt=0)
    model_name: str = Field(min_length=1, max_length=160)
    roles: list[str] = Field(min_length=1, max_length=5)

class AgentLLMRouteOut(BaseModel):
    role: str
    source_id: int | None
    source_name: str
    provider: str
    model_name: str
    environment_fallback: bool = False

class LLMSettingsOut(BaseModel):
    encryption_key_ready: bool
    sources: list[LLMSourceOut] = Field(default_factory=list)
    routes: list[AgentLLMRouteOut] = Field(default_factory=list)

class LLMModelsOut(BaseModel):
    models: list[str] = Field(default_factory=list)


class EvidenceRecordCreate(BaseModel):
    claim: str = Field(min_length=3, max_length=4000)
    category: EvidenceCategory
    classification: EvidenceClassification = "unknown"
    source_provider: Literal[
        "manual",
        "pubmed",
        "clinicaltrials",
        "openfda",
        "tavily",
    ] = "manual"
    source_title: str = Field(default="", max_length=500)
    source_reference: str = Field(default="", max_length=500)
    source_url: str = Field(default="", max_length=2000)
    publication_date: date | None = None
    retrieved_at: datetime | None = None
    evidence_quality: EvidenceQuality = "unassessed"
    limitations: str = Field(default="", max_length=4000)
    source_excerpt: str = Field(default="", max_length=6000)
    relying_executives: list[ExecutiveRoleName] = Field(default_factory=list)
    challenged: bool = False
    disputed: bool = False
    dispute_notes: str = Field(default="", max_length=4000)
    verification_note: str = Field(default="", max_length=2000)
    meeting_ids: list[int] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def require_verification_provenance(self):
        if self.classification == "verified" and (
            not (self.source_url or self.source_reference)
            or not self.verification_note.strip()
        ):
            raise ValueError(
                "Verified claims require a source reference or URL and a verification note."
            )
        return self


class EvidenceRecordUpdate(BaseModel):
    claim: str | None = Field(default=None, min_length=3, max_length=4000)
    category: EvidenceCategory | None = None
    classification: EvidenceClassification | None = None
    source_provider: Literal[
        "manual",
        "pubmed",
        "clinicaltrials",
        "openfda",
        "tavily",
    ] | None = None
    source_title: str | None = Field(default=None, max_length=500)
    source_reference: str | None = Field(default=None, max_length=500)
    source_url: str | None = Field(default=None, max_length=2000)
    publication_date: date | None = None
    retrieved_at: datetime | None = None
    evidence_quality: EvidenceQuality | None = None
    limitations: str | None = Field(default=None, max_length=4000)
    source_excerpt: str | None = Field(default=None, max_length=6000)
    relying_executives: list[ExecutiveRoleName] | None = None
    challenged: bool | None = None
    disputed: bool | None = None
    dispute_notes: str | None = Field(default=None, max_length=4000)
    verification_note: str | None = Field(default=None, max_length=2000)
    meeting_ids: list[int] | None = Field(default=None, max_length=50)


class EvidenceRecordOut(BaseModel):
    id: int
    claim: str
    category: EvidenceCategory
    classification: EvidenceClassification
    source_provider: Literal["manual", "pubmed", "clinicaltrials", "openfda", "tavily"]
    source_title: str
    source_reference: str
    source_url: str
    publication_date: date | None
    retrieved_at: datetime | None
    evidence_quality: EvidenceQuality
    limitations: str
    source_excerpt: str
    relying_executives: list[ExecutiveRoleName]
    challenged: bool
    challenged_by: list[ExecutiveRoleName]
    disputed: bool
    disputed_by: list[ExecutiveRoleName]
    dispute_notes: str
    verification_note: str
    meeting_ids: list[int] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ResearchSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    providers: list[Literal["pubmed", "clinicaltrials", "openfda", "tavily"]] = Field(
        default_factory=lambda: ["pubmed", "clinicaltrials", "openfda"],
        min_length=1,
        max_length=4,
    )
    limit_per_provider: int = Field(default=5, ge=1, le=10)


class ResearchSourceOut(BaseModel):
    provider: str
    title: str
    url: str
    source_reference: str = ""
    publication_date: date | None = None
    retrieved_at: datetime
    excerpt: str = ""
    limitations: str


class ResearchSearchOut(BaseModel):
    query: str
    results: list[ResearchSourceOut]
    warnings: list[str] = Field(default_factory=list)
    web_search_configured: bool


class ResearchSettingsOut(BaseModel):
    web_search_configured: bool
    encryption_key_ready: bool


class TavilyKeyUpdate(BaseModel):
    api_key: SecretStr | None = None
    clear_api_key: bool = False

DecisionConditionStatus = Literal["pending", "met", "breached"]
DecisionLifecycleName = Literal["open", "under_review", "closed", "superseded"]


class DecisionCondition(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:8], max_length=40)
    label: str = Field(min_length=1, max_length=300)
    status: DecisionConditionStatus = "pending"
    note: str = Field(default="", max_length=1000)
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def ensure_condition_id(self):
        if not self.id:
            self.id = uuid4().hex[:8]
        return self


class DecisionRecordCreate(BaseModel):
    meeting_id: int | None = Field(default=None, gt=0)
    decision: str = Field(min_length=1, max_length=2000)
    rationale: str = ""
    board_recommendation: str = ""
    founder_decision: str = ""
    founder_notes: str = ""
    conditions: list[DecisionCondition] = Field(default_factory=list, max_length=50)
    owner: str = Field(default="", max_length=200)
    target_date: date | None = None
    success_criteria: str = ""
    review_date: date | None = None
    actual_outcome: str = ""
    lifecycle: DecisionLifecycleName = "open"


class DecisionRecordUpdate(BaseModel):
    decision: str | None = Field(default=None, min_length=1, max_length=2000)
    rationale: str | None = None
    board_recommendation: str | None = None
    founder_decision: str | None = None
    founder_notes: str | None = None
    conditions: list[DecisionCondition] | None = None
    owner: str | None = None
    target_date: date | None = None
    success_criteria: str | None = None
    review_date: date | None = None
    actual_outcome: str | None = None
    lifecycle: DecisionLifecycleName | None = None


class DecisionRecordOut(BaseModel):
    id: int
    meeting_id: int | None
    meeting_title: str = ""
    decision: str
    rationale: str
    board_recommendation: str
    founder_decision: str
    founder_notes: str
    conditions: list[DecisionCondition]
    owner: str
    target_date: date | None
    success_criteria: str
    review_date: date | None
    actual_outcome: str
    lifecycle: str
    last_reviewed_at: datetime | None
    review_notes: str
    is_review_due: bool
    created_at: datetime
    updated_at: datetime


class DecisionReviewIn(BaseModel):
    outcome: str = ""
    notes: str = ""
    new_review_date: date | None = None
    lifecycle: DecisionLifecycleName | None = None
    conditions: list[DecisionCondition] | None = None


class MemoryRecordOut(BaseModel):
    id: int
    meeting_id: int | None
    meeting_title: str = ""
    decision: str
    founder_decision: str
    lifecycle: str
    success_criteria: str
    review_date: date | None
    actual_outcome: str
    score: float


class MemoryRecallOut(BaseModel):
    query: str
    records: list[MemoryRecordOut]
    context_block: str
    total_matches: int


PriorityStatusName = Literal["active", "paused", "achieved"]
ConstraintSeverityName = Literal["low", "medium", "high"]


class CompanyPriorityIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=2000)
    status: PriorityStatusName = "active"
    target_date: date | None = None


class CompanyPriorityUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    status: PriorityStatusName | None = None
    target_date: date | None = None


class CompanyPriorityOut(CompanyPriorityIn):
    id: str


class CompanyConstraintIn(BaseModel):
    label: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=2000)
    severity: ConstraintSeverityName = "medium"


class CompanyConstraintUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    severity: ConstraintSeverityName | None = None


class CompanyConstraintOut(CompanyConstraintIn):
    id: str


class CompanyFinancialAssumptionIn(BaseModel):
    label: str = Field(min_length=2, max_length=200)
    value: str = Field(default="", max_length=120)
    unit: str = Field(default="", max_length=64)
    note: str = Field(default="", max_length=1000)


class CompanyFinancialAssumptionUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=2, max_length=200)
    value: str | None = Field(default=None, max_length=120)
    unit: str | None = Field(default=None, max_length=64)
    note: str | None = Field(default=None, max_length=1000)


class CompanyFinancialAssumptionOut(CompanyFinancialAssumptionIn):
    id: str


class CompanyKnowledgeIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    summary: str = Field(default="", max_length=4000)
    category: str = Field(default="operational", max_length=32)
    source_reference: str = Field(default="", max_length=500)
    evidence_id: int | None = None


class CompanyKnowledgeUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    summary: str | None = Field(default=None, max_length=4000)
    category: str | None = Field(default=None, max_length=32)
    source_reference: str | None = Field(default=None, max_length=500)
    evidence_id: int | None = None


class CompanyKnowledgeOut(BaseModel):
    id: str
    title: str
    summary: str
    category: str
    source_reference: str
    evidence_id: int | None
    approved_at: str | None = None


class CompanyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    mission: str | None = Field(default=None, max_length=4000)
    strategic_context: str | None = Field(default=None, max_length=8000)
    owner: str | None = Field(default=None, max_length=160)
    stage: str | None = Field(default=None, max_length=40)
    onboarded: bool | None = None


class CompanyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    mission: str = Field(default="", max_length=4000)
    strategic_context: str = Field(default="", max_length=8000)
    owner: str = Field(default="Founder", max_length=160)
    stage: str = Field(default="", max_length=40)
    onboarded: bool = False
    seed_starters: bool = False


class CompanyOut(BaseModel):
    id: int
    name: str
    mission: str
    strategic_context: str
    owner: str
    stage: str
    onboarded: bool = False
    strategic_priorities: list[CompanyPriorityOut]
    constraints: list[CompanyConstraintOut]
    financial_assumptions: list[CompanyFinancialAssumptionOut]
    approved_knowledge: list[CompanyKnowledgeOut]
    created_at: datetime
    updated_at: datetime | None


class CompanyCountsOut(BaseModel):
    meetings_total: int = 0
    meetings_completed: int = 0
    meetings_running: int = 0
    decisions_total: int = 0
    decisions_open: int = 0
    decisions_due: int = 0
    decisions_closed: int = 0
    evidence_total: int = 0
    knowledge_approved: int = 0


class CompanyProfileOut(CompanyOut):
    counts: CompanyCountsOut = Field(default_factory=CompanyCountsOut)


class CompanyRiskOut(BaseModel):
    kind: str
    title: str
    detail: str = ""
    severity: str = "medium"
    decision_id: int | None = None
    constraint_id: str | None = None


class RecentMeetingOut(BaseModel):
    id: int
    title: str
    status: str
    created_at: datetime


class CompanyContextOut(BaseModel):
    company: CompanyOut
    counts: CompanyCountsOut
    risks: list[CompanyRiskOut] = Field(default_factory=list)
    recent_decisions: list[DecisionRecordOut] = Field(default_factory=list)
    recent_meetings: list[RecentMeetingOut] = Field(default_factory=list)


class GovernanceEventOut(BaseModel):
    id: int
    meeting_id: int
    meeting_title: str
    action: str
    actor: str
    comments: str
    created_at: datetime


class GovernanceOut(BaseModel):
    events: list[GovernanceEventOut] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    policy: dict[str, str] = Field(default_factory=dict)


class ExecutivePerformanceOut(BaseModel):
    role: str
    assessments: int = 0
    challenges: int = 0
    revisions: int = 0
    models: list[str] = Field(default_factory=list)
    last_active_at: datetime | None = None


class DecisionOutcomeOut(BaseModel):
    decision_id: int
    decision: str
    founder_decision: str
    lifecycle: str
    review_date: date | None
    actual_outcome: str
    updated_at: datetime


class PerformanceOut(BaseModel):
    decisions_total: int = 0
    decisions_with_outcome: int = 0
    approved: int = 0
    rejected: int = 0
    deferred: int = 0
    revision_requested: int = 0
    open_decisions: int = 0
    due_decisions: int = 0
    meetings_total: int = 0
    meetings_completed: int = 0
    executives: list[ExecutivePerformanceOut] = Field(default_factory=list)
    recent_outcomes: list[DecisionOutcomeOut] = Field(default_factory=list)
    scorecards: list["ExecutiveScorecardOut"] = Field(default_factory=list)
    metric_definitions: list[dict[str, Any]] = Field(default_factory=list)
    feedback_policy: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Programme 5 — Executive scorecard and founder feedback
# ---------------------------------------------------------------------------

FeedbackDimension = Literal[
    "evidence_discipline",
    "mandate_adherence",
    "challenge_quality",
    "position_integrity",
    "specificity",
    "forecast_accuracy",
    "decision_usefulness",
]


class ScoreMetricOut(BaseModel):
    key: str
    label: str
    description: str
    signal: str
    score: float | None = None
    sample_size: int = 0
    note: str = ""


class ExecutiveScorecardOut(BaseModel):
    role: str
    overall_score: float | None = None
    trend: float | None = None
    metrics: list[ScoreMetricOut] = Field(default_factory=list)
    contributions: int = 0
    feedback_count: int = 0
    last_active_at: datetime | None = None


class ExecutiveFeedbackIn(BaseModel):
    role: Literal["CEO", "CFO", "CTO", "CSO"]
    dimension: FeedbackDimension
    rating: int = Field(ge=1, le=5)
    meeting_id: int | None = None
    contribution_id: int | None = None
    notes: str = Field(default="", max_length=2000)


class ExecutiveFeedbackOut(BaseModel):
    id: int
    role: str
    dimension: str
    rating: int
    meeting_id: int | None
    contribution_id: int | None
    notes: str
    actor: str
    created_at: datetime
    updated_at: datetime


class ContributionReviewOut(BaseModel):
    contribution_id: int
    role: str
    meeting_id: int | None
    meeting_title: str
    created_at: datetime
    assessment_excerpt: str
    challenge_excerpt: str
    revision_excerpt: str
    feedback: list[ExecutiveFeedbackOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Programme 6 — Controlled operational capabilities
# ---------------------------------------------------------------------------

ArtifactKind = Literal[
    "project_plan",
    "financial_model",
    "investor_document",
    "task_list",
    "architecture_document",
    "milestone_review",
    "company_review",
]


class OperationalArtifactCreate(BaseModel):
    kind: ArtifactKind
    title: str = Field(min_length=2, max_length=200)
    brief: str = Field(default="", max_length=6000)
    meeting_id: int | None = None
    decision_id: int | None = None
    external_actions: bool = False


class OperationalArtifactOut(BaseModel):
    id: int
    kind: str
    title: str
    brief: str
    status: str
    payload: dict[str, Any] = Field(default_factory=dict)
    permissions: dict[str, Any] = Field(default_factory=dict)
    meeting_id: int | None
    decision_id: int | None
    created_by: str
    approved_by: str | None
    approved_at: datetime | None
    rejection_reason: str
    created_at: datetime
    updated_at: datetime
    events: list["OperationalEventOut"] = Field(default_factory=list)


class OperationalEventOut(BaseModel):
    id: int
    action: str
    actor: str
    comments: str
    created_at: datetime


class OperationalCommentIn(BaseModel):
    comments: str = Field(default="", max_length=2000)


class CapabilityOut(BaseModel):
    kind: str
    label: str
    description: str
    permission: str
    external: bool
    approval_required: bool
    enabled: bool


class CapabilitiesOut(BaseModel):
    capabilities: list[CapabilityOut]
    policy: dict[str, Any]


OperationalArtifactOut.model_rebuild()
PerformanceOut.model_rebuild()
