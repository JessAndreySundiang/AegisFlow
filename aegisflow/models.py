"""Pydantic v2 domain models shared by agents, graph, database, and UI."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utcnow_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TaskStatus(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    FAILED = "failed"
    AWAITING_HUMAN_REVIEW = "awaiting_human_review"
    REVISION_REQUESTED = "revision_requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"


TERMINAL_STATUSES = {
    TaskStatus.BLOCKED,
    TaskStatus.FAILED,
    TaskStatus.REJECTED,
    TaskStatus.COMPLETED,
}

ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {TaskStatus.PLANNING, TaskStatus.BLOCKED, TaskStatus.FAILED},
    TaskStatus.PLANNING: {
        TaskStatus.IN_PROGRESS,
        TaskStatus.BLOCKED,
        TaskStatus.FAILED,
    },
    TaskStatus.IN_PROGRESS: {
        TaskStatus.AWAITING_HUMAN_REVIEW,
        TaskStatus.BLOCKED,
        TaskStatus.FAILED,
        TaskStatus.REVISION_REQUESTED,
    },
    TaskStatus.AWAITING_HUMAN_REVIEW: {
        TaskStatus.APPROVED,
        TaskStatus.REJECTED,
        TaskStatus.REVISION_REQUESTED,
        TaskStatus.FAILED,
    },
    TaskStatus.REVISION_REQUESTED: {
        TaskStatus.IN_PROGRESS,
        TaskStatus.AWAITING_HUMAN_REVIEW,
        TaskStatus.FAILED,
        TaskStatus.BLOCKED,
    },
    TaskStatus.APPROVED: {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.AWAITING_HUMAN_REVIEW},
    TaskStatus.COMPLETED: set(),
    TaskStatus.REJECTED: set(),
    TaskStatus.BLOCKED: set(),
    TaskStatus.FAILED: set(),
}


class SubtaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class AgentStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    ESCALATED = "escalated"


class ClaimStatus(str, Enum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    CONFLICTING = "conflicting"
    UNVERIFIED = "unverified"


class ReviewDecision(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NEEDS_REVISION = "needs_revision"


class HumanDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_REVISION = "request_revision"


class FileStatus(str, Enum):
    OK = "ok"
    EMPTY = "empty"
    ENCRYPTED = "encrypted"
    CORRUPTED = "corrupted"
    UNSUPPORTED = "unsupported"
    TOO_LARGE = "too_large"


class OutputSource(str, Enum):
    AGENT = "agent"
    HUMAN_EDIT = "human_edit"


class ErrorClass(str, Enum):
    TRANSIENT = "transient"
    MALFORMED_OUTPUT = "malformed_output"
    MISSING_INPUT = "missing_input"
    POLICY_VIOLATION = "policy_violation"
    CONFIGURATION = "configuration"
    UNKNOWN = "unknown"


TaskType = Literal["summary", "report", "meeting_brief", "outline", "action_items"]
OutputFormat = Literal["markdown", "txt"]


class FileMeta(StrictModel):
    file_id: str
    filename: str
    extension: str
    size_bytes: int
    sha256: str = ""
    pages: int | None = None
    status: FileStatus = FileStatus.OK
    message: str = ""
    stored_path: str = ""


class Claim(StrictModel):
    id: str
    text: str
    source_ref: str = ""
    status: ClaimStatus = ClaimStatus.UNVERIFIED
    rationale: str = ""

    @field_validator("text")
    @classmethod
    def text_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("claim text cannot be empty")
        return value


class EvidenceRef(StrictModel):
    id: str
    file_id: str = ""
    filename: str
    location: str
    excerpt: str = ""


class AnalysisResult(StrictModel):
    summary: str
    findings: list[Claim] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)


class VerificationResult(StrictModel):
    claims: list[Claim] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)


class PlanSubtask(StrictModel):
    id: str
    title: str
    description: str
    assigned_agent: Literal[
        "document_analyst", "evidence_verifier", "report_writer"
    ]
    skill: Literal[
        "document-extraction", "evidence-verification", "report-writing"
    ]
    depends_on: list[str] = Field(default_factory=list)
    required: bool = True

    @field_validator("id")
    @classmethod
    def valid_id(cls, value: str) -> str:
        if not value or not value.replace("-", "").replace("_", "").isalnum():
            raise ValueError("subtask id must be alphanumeric (hyphens/underscores allowed)")
        return value


class Plan(StrictModel):
    task_type: TaskType
    objective: str
    subtasks: list[PlanSubtask] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def coherent(self) -> Plan:
        if not self.missing_information and not self.subtasks:
            raise ValueError("a plan needs at least one subtask unless it is blocked")
        if self.missing_information and self.subtasks:
            raise ValueError("a blocked plan must not contain executable subtasks")
        ids = [s.id for s in self.subtasks]
        if len(ids) != len(set(ids)):
            raise ValueError("subtask ids must be unique")
        for subtask in self.subtasks:
            missing = [d for d in subtask.depends_on if d not in ids]
            if missing:
                raise ValueError(
                    f"subtask {subtask.id} depends on unknown subtasks: {missing}"
                )
            if subtask.id in subtask.depends_on:
                raise ValueError(f"subtask {subtask.id} cannot depend on itself")
        return self


class PolicyFinding(StrictModel):
    rule_id: str
    severity: Literal["info", "warning", "high"]
    message: str
    location: str = ""


class PolicyReport(StrictModel):
    passed: bool
    findings: list[PolicyFinding] = Field(default_factory=list)
    checks_run: list[str] = Field(default_factory=list)

    @property
    def high_severity_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "high")


class ReviewResult(StrictModel):
    decision: ReviewDecision
    reasons: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    plan_alignment: str = ""
    policy_consistency: str = ""
    simulated: bool = False


class AgentResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    agent: str
    level: int
    skill: str
    status: AgentStatus
    summary: str = ""
    output: dict[str, Any] = Field(default_factory=dict)
    claims: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)
    error_class: str = ""
    retries: int = 0
    simulated: bool = True
    started_at: str = Field(default_factory=utcnow_iso)
    finished_at: str = Field(default_factory=utcnow_iso)


class OutputVersion(BaseModel):
    id: str
    task_id: str
    version_number: int
    content: str
    content_hash: str
    source: OutputSource
    validation_status: str = "pending"
    simulated: bool = True
    created_at: str = Field(default_factory=utcnow_iso)


class ApprovalRecord(BaseModel):
    id: str
    task_id: str
    version_id: str
    version_number: int
    content_hash: str
    decision: HumanDecision
    feedback: str = ""
    reviewer: str
    actor: str
    created_at: str = Field(default_factory=utcnow_iso)


class HumanReview(BaseModel):
    id: str
    task_id: str
    version_id: str
    content_hash: str
    decision: HumanDecision
    feedback: str = ""
    reviewer: str
    actor: str = ""
    created_at: str = Field(default_factory=utcnow_iso)


class AuditEvent(BaseModel):
    id: str
    task_id: str
    event_type: str
    actor: str
    rule_id: str | None = None
    detail: str = ""
    created_at: str = Field(default_factory=utcnow_iso)


class RoutingDecision(StrictModel):
    from_node: str
    to_node: str
    reason: str
    rule: str = ""
    depth: int = 1


class TaskRecord(BaseModel):
    id: str
    request: str
    output_format: OutputFormat
    status: TaskStatus
    simulated: bool
    manual_minutes: float | None = None
    elapsed_seconds: float | None = None
    escalation_reason: str = ""
    current_version_id: str | None = None
    created_at: str
    updated_at: str


class WorkloadMetric(BaseModel):
    task_id: str
    manual_minutes: float | None = None
    elapsed_seconds: float | None = None
    subtasks_completed: int = 0
    revisions_requested: int = 0
    approval_outcome: str = ""
    quality_rating: int | None = None
    time_reduction_pct: float | None = None
    created_at: str = Field(default_factory=utcnow_iso)
