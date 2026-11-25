import enum
from datetime import date, datetime, timezone
from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    String,
    Text,
    DateTime,
    ForeignKey,
    Enum,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

def utcnow():
    return datetime.now(timezone.utc)

class MeetingStatus(str, enum.Enum):
    draft = "draft"
    running = "running"
    completed = "completed"
    failed = "failed"

class DecisionStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    revision_requested = "revision_requested"
    deferred = "deferred"

class DecisionLifecycle(str, enum.Enum):
    open = "open"
    under_review = "under_review"
    closed = "closed"
    superseded = "superseded"

class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), default="Neurotechnology Venture")
    mission: Mapped[str] = mapped_column(Text, default="")
    strategic_context: Mapped[str] = mapped_column(Text, default="")
    owner: Mapped[str] = mapped_column(String(160), default="")
    owner_user_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    onboarded: Mapped[bool] = mapped_column(Boolean, default=False)
    stage: Mapped[str] = mapped_column(String(40), default="")
    strategic_priorities: Mapped[list[dict]] = mapped_column(JSON, default=list)
    constraints: Mapped[list[dict]] = mapped_column(JSON, default=list)
    financial_assumptions: Mapped[list[dict]] = mapped_column(JSON, default=list)
    approved_knowledge: Mapped[list[dict]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=True,
    )

class Executive(Base):
    __tablename__ = "executives"
    id: Mapped[int] = mapped_column(primary_key=True)
    role: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(120))
    mandate: Mapped[str] = mapped_column(Text)
    system_instruction: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class LLMSource(Base):
    __tablename__ = "llm_sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    provider: Mapped[str] = mapped_column(String(32), index=True)
    base_url: Mapped[str] = mapped_column(String(500))
    encrypted_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    routes: Mapped[list["AgentLLMRoute"]] = relationship(back_populates="source")

class AgentLLMRoute(Base):
    __tablename__ = "agent_llm_routes"
    role: Mapped[str] = mapped_column(String(32), primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("llm_sources.id", ondelete="RESTRICT"))
    model_name: Mapped[str] = mapped_column(String(160))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    source: Mapped["LLMSource"] = relationship(back_populates="routes")

class BoardMeeting(Base):
    __tablename__ = "board_meetings"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), index=True, nullable=True
    )
    title: Mapped[str] = mapped_column(String(240))
    agenda: Mapped[str] = mapped_column(Text)
    founder_context: Mapped[str] = mapped_column(Text, default="")
    include_memory: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[MeetingStatus] = mapped_column(Enum(MeetingStatus), default=MeetingStatus.draft)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    contributions: Mapped[list["AgentContribution"]] = relationship(back_populates="meeting", cascade="all, delete-orphan")
    resolution: Mapped["BoardResolution | None"] = relationship(back_populates="meeting", uselist=False, cascade="all, delete-orphan")
    run_events: Mapped[list["MeetingRunEvent"]] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
        order_by="MeetingRunEvent.id",
    )
    run_checkpoints: Mapped[list["MeetingRunCheckpoint"]] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
        order_by="MeetingRunCheckpoint.id",
    )
    evidence_links: Mapped[list["MeetingEvidenceLink"]] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
    )

class MeetingRunEvent(Base):
    __tablename__ = "meeting_run_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("board_meetings.id", ondelete="CASCADE"), index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    event_type: Mapped[str] = mapped_column(String(32))
    phase: Mapped[str] = mapped_column(String(32))
    role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    meeting: Mapped["BoardMeeting"] = relationship(back_populates="run_events")

class MeetingRunCheckpoint(Base):
    __tablename__ = "meeting_run_checkpoints"
    __table_args__ = (
        UniqueConstraint("meeting_id", "phase", "role", name="uq_meeting_checkpoint_phase_role"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("board_meetings.id", ondelete="CASCADE"), index=True)
    phase: Mapped[str] = mapped_column(String(32))
    role: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    model_provider: Mapped[str] = mapped_column(String(32), default="unknown")
    model_name: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    meeting: Mapped["BoardMeeting"] = relationship(back_populates="run_checkpoints")

class AgentContribution(Base):
    __tablename__ = "agent_contributions"
    __table_args__ = (UniqueConstraint("meeting_id", "role", "phase", name="uq_meeting_role_phase"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("board_meetings.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(32), index=True)
    phase: Mapped[str] = mapped_column(String(32), default="assessment")
    assessment: Mapped[str] = mapped_column(Text, default="")
    critique: Mapped[str] = mapped_column(Text, default="")
    model_provider: Mapped[str] = mapped_column(String(32), default="local")
    model_name: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    meeting: Mapped["BoardMeeting"] = relationship(back_populates="contributions")

    @property
    def revision(self) -> str | None:
        return next(
            (
                checkpoint.content
                for checkpoint in self.meeting.run_checkpoints
                if checkpoint.phase == "revision" and checkpoint.role == self.role
            ),
            None,
        )

class BoardResolution(Base):
    __tablename__ = "board_resolutions"
    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("board_meetings.id", ondelete="CASCADE"), unique=True)
    recommendation: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text, default="")
    dissent_and_open_questions: Mapped[str] = mapped_column(Text, default="")
    decision_status: Mapped[DecisionStatus] = mapped_column(Enum(DecisionStatus), default=DecisionStatus.pending)
    founder_notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meeting: Mapped["BoardMeeting"] = relationship(back_populates="resolution")

class EvidenceRecord(Base):
    __tablename__ = "evidence_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), index=True, nullable=True
    )
    claim: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(32), index=True)
    classification: Mapped[str] = mapped_column(String(32), index=True)
    source_provider: Mapped[str] = mapped_column(String(32), default="manual")
    source_title: Mapped[str] = mapped_column(String(500), default="")
    source_reference: Mapped[str] = mapped_column(String(500), default="")
    source_url: Mapped[str] = mapped_column(String(2000), default="")
    publication_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence_quality: Mapped[str] = mapped_column(String(24), default="unassessed")
    limitations: Mapped[str] = mapped_column(Text, default="")
    source_excerpt: Mapped[str] = mapped_column(Text, default="")
    relying_executives: Mapped[list[str]] = mapped_column(JSON, default=list)
    challenged: Mapped[bool] = mapped_column(Boolean, default=False)
    challenged_by: Mapped[list[str]] = mapped_column(JSON, default=list)
    disputed: Mapped[bool] = mapped_column(Boolean, default=False)
    disputed_by: Mapped[list[str]] = mapped_column(JSON, default=list)
    dispute_notes: Mapped[str] = mapped_column(Text, default="")
    verification_note: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    meeting_links: Mapped[list["MeetingEvidenceLink"]] = relationship(
        back_populates="evidence",
        cascade="all, delete-orphan",
    )

class MeetingEvidenceLink(Base):
    __tablename__ = "meeting_evidence_links"
    __table_args__ = (
        UniqueConstraint("meeting_id", "evidence_id", name="uq_meeting_evidence_link"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(
        ForeignKey("board_meetings.id", ondelete="CASCADE"),
        index=True,
    )
    evidence_id: Mapped[int] = mapped_column(
        ForeignKey("evidence_records.id", ondelete="CASCADE"),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    meeting: Mapped["BoardMeeting"] = relationship(back_populates="evidence_links")
    evidence: Mapped["EvidenceRecord"] = relationship(back_populates="meeting_links")

class ResearchProviderConfig(Base):
    __tablename__ = "research_provider_configs"
    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), unique=True)
    encrypted_api_key: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class ApprovalEvent(Base):
    __tablename__ = "approval_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("board_meetings.id", ondelete="CASCADE"))
    action: Mapped[str] = mapped_column(String(40))
    actor: Mapped[str] = mapped_column(String(120), default="Founder")
    comments: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class DecisionRecord(Base):
    __tablename__ = "decision_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), index=True, nullable=True
    )
    meeting_id: Mapped[int | None] = mapped_column(
        ForeignKey("board_meetings.id", ondelete="SET NULL"),
        unique=True,
        index=True,
        nullable=True,
    )
    decision: Mapped[str] = mapped_column(Text, default="")
    rationale: Mapped[str] = mapped_column(Text, default="")
    board_recommendation: Mapped[str] = mapped_column(Text, default="")
    founder_decision: Mapped[str] = mapped_column(String(32), default="")
    founder_notes: Mapped[str] = mapped_column(Text, default="")
    conditions: Mapped[list[dict]] = mapped_column(JSON, default=list)
    owner: Mapped[str] = mapped_column(String(200), default="")
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    success_criteria: Mapped[str] = mapped_column(Text, default="")
    review_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_outcome: Mapped[str] = mapped_column(Text, default="")
    lifecycle: Mapped[DecisionLifecycle] = mapped_column(
        Enum(DecisionLifecycle),
        default=DecisionLifecycle.open,
    )
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    meeting: Mapped["BoardMeeting | None"] = relationship()

class ExecutiveFeedback(Base):
    """Founder feedback on an individual executive contribution.

    Deliberately quality-focused: there is no field for agreement with the
    founder, so feedback cannot become a sycophancy incentive.
    """

    __tablename__ = "executive_feedback"
    __table_args__ = (
        UniqueConstraint(
            "meeting_id", "role", "dimension", name="uq_feedback_meeting_role_dimension"
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), index=True, nullable=True
    )
    role: Mapped[str] = mapped_column(String(32), index=True)
    meeting_id: Mapped[int | None] = mapped_column(
        ForeignKey("board_meetings.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    contribution_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_contributions.id", ondelete="SET NULL"),
        nullable=True,
    )
    dimension: Mapped[str] = mapped_column(String(40), index=True)
    rating: Mapped[int] = mapped_column(Integer)
    notes: Mapped[str] = mapped_column(Text, default="")
    actor: Mapped[str] = mapped_column(String(120), default="Founder")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class OperationalArtifact(Base):
    """A permissioned, draft-only operational deliverable.

    Nothing here performs an external action. Artifacts move from draft to
    pending approval, and only a founder approval makes them usable.
    """

    __tablename__ = "operational_artifacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), index=True, nullable=True
    )
    kind: Mapped[str] = mapped_column(String(48), index=True)
    title: Mapped[str] = mapped_column(String(200))
    brief: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    permissions: Mapped[dict] = mapped_column(JSON, default=dict)
    meeting_id: Mapped[int | None] = mapped_column(
        ForeignKey("board_meetings.id", ondelete="SET NULL"), nullable=True
    )
    decision_id: Mapped[int | None] = mapped_column(
        ForeignKey("decision_records.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[str] = mapped_column(String(120), default="Founder")
    approved_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejection_reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class OperationalEvent(Base):
    """Immutable audit trail for operational artifacts."""

    __tablename__ = "operational_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    artifact_id: Mapped[int] = mapped_column(
        ForeignKey("operational_artifacts.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[str] = mapped_column(String(40))
    actor: Mapped[str] = mapped_column(String(120), default="Founder")
    comments: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
