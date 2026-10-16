"""
Domain models and schema definitions for Task 3: Meeting to Scope.
Covers extracted requirements, capability assessments, scope of work,
task breakdowns with hour estimates, proposals, change detection, and review decisions.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class RequirementType(str, Enum):
    FUNCTIONAL = "functional"
    NON_FUNCTIONAL = "non_functional"
    INTEGRATION = "integration"
    CONFIGURATION = "configuration"
    CUSTOM_DEVELOPMENT = "custom_development"


class RequirementCertainty(str, Enum):
    EXPLICIT_FACT = "explicit_fact"
    INTERPRETATION = "interpretation"
    ASSUMPTION = "assumption"
    UNCONFIRMED = "unconfirmed"


class RequirementStatus(str, Enum):
    CONFIRMED = "confirmed"
    CLARIFIED = "clarified"
    MODIFIED = "modified"
    ADDED = "added"
    REMOVED = "removed"
    OUT_OF_SCOPE = "out_of_scope"
    NEEDS_CLARIFICATION = "needs_clarification"


class CapabilityStatus(str, Enum):
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"
    UNCERTAIN = "uncertain"
    NEEDS_EXPERT_REVIEW = "needs_expert_review"


class WorkType(str, Enum):
    CONFIGURATION = "configuration"
    INTEGRATION = "integration"
    CUSTOM_DEVELOPMENT = "custom_development"
    TESTING = "testing"
    DEPLOYMENT = "deployment"


class EstimateConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    PROVISIONAL = "provisional"


class ProposalStatus(str, Enum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class ReviewAction(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    EDIT = "edit"
    REQUEST_CLARIFICATION = "request_clarification"


class ExtractedRequirement(BaseModel):
    """A granular client requirement extracted from a meeting transcript."""
    id: str = Field(..., description="Unique stable identifier, e.g. REQ-001")
    title: str = Field(..., description="Concise requirement title")
    description: str = Field(..., description="Detailed description of client need")
    req_type: RequirementType = Field(default=RequirementType.FUNCTIONAL)
    certainty: RequirementCertainty = Field(default=RequirementCertainty.EXPLICIT_FACT)
    status: RequirementStatus = Field(default=RequirementStatus.CONFIRMED)
    transcript_evidence: Optional[str] = Field(
        default=None,
        description="Exact quote or reference from transcript supporting this requirement"
    )
    user_roles: List[str] = Field(default_factory=list, description="Target user roles or personas")
    clarification_question: Optional[str] = Field(
        default=None,
        description="Clarification question if the requirement is ambiguous or incomplete"
    )
    is_conflicting: bool = Field(default=False, description="True if this conflicts with another statement")
    conflict_notes: Optional[str] = None


class CapabilityAssessment(BaseModel):
    """Investigation of whether a requirement can be fulfilled by Brilliant Directories."""
    requirement_id: str
    status: CapabilityStatus = Field(default=CapabilityStatus.UNCERTAIN)
    native_feature_name: Optional[str] = Field(default=None, description="Identified native feature or add-on")
    configuration_path: Optional[str] = Field(default=None, description="Admin navigation path")
    documentation_urls: List[str] = Field(default_factory=list, description="Source article URLs from Knowledge Brain")
    evidence_summary: str = Field(..., description="What the documentation supports")
    uncertainty_notes: Optional[str] = Field(default=None, description="What remains uncertain or requires verification")
    recommended_approach: str = Field(
        default="configuration",
        description="configuration | custom_development | hybrid | unsupported"
    )
    requires_expert_review: bool = Field(default=False)
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Task 1 capability match confidence score between 0.0 and 1.0"
    )


class TaskEstimate(BaseModel):
    """An implementation task with bottom-up hour estimate."""
    task_id: str = Field(..., description="Unique task identifier, e.g. TSK-001")
    title: str = Field(..., description="Task title")
    description: str = Field(..., description="Detailed implementation steps")
    linked_requirement_ids: List[str] = Field(default_factory=list)
    work_type: WorkType = Field(default=WorkType.CONFIGURATION)
    estimated_hours: float = Field(..., ge=0.0, description="Estimated hours (must be >= 0)")
    estimation_rationale: str = Field(..., description="Why this effort is estimated")
    confidence: EstimateConfidence = Field(default=EstimateConfidence.MEDIUM)
    confidence_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Numeric confidence score between 0.0 and 1.0"
    )
    dependencies: List[str] = Field(default_factory=list, description="IDs of prerequisite tasks")
    acceptance_criteria: List[str] = Field(default_factory=list)
    is_provisional: bool = Field(default=False, description="True if requirement is awaiting clarification")


class ChangeItem(BaseModel):
    """A classified change between an original scope and a follow-up meeting."""
    change_id: str = Field(..., description="Unique identifier for this change, e.g. CHG-001")
    classification: RequirementStatus = Field(
        ...,
        description="unchanged | clarified | modified | added | removed | out_of_scope | needs_clarification"
    )
    original_requirement_id: Optional[str] = None
    original_text: Optional[str] = None
    revised_text: Optional[str] = None
    transcript_evidence: str = Field(..., description="Quote from follow-up transcript demonstrating change")
    reason: str = Field(..., description="Explanation of why change was classified this way")
    hour_delta: float = Field(default=0.0, description="Change in estimated hours (+ or -)")
    new_dependencies: List[str] = Field(default_factory=list)
    new_risks: List[str] = Field(default_factory=list)
    human_approval_required: bool = Field(default=True)


class ChangeDetectionReport(BaseModel):
    """Comparison report comparing follow-up meeting with baseline scope."""
    report_id: str
    project_id: str
    original_version: str
    follow_up_version: str
    summary: str
    total_original_hours: float
    total_revised_hours: float
    net_hour_delta: float
    changes: List[ChangeItem] = Field(default_factory=list)
    out_of_scope_requests: List[ChangeItem] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ScopeOfWork(BaseModel):
    """Structured software implementation scope of work."""
    scope_id: str
    project_id: str
    version: str = Field(default="v1.0", description="v1.0 for initial, v1.1/v2.0 for follow-ups")
    project_title: str
    client_objectives: List[str] = Field(default_factory=list)
    current_workflow_summary: Optional[str] = None
    requirements: List[ExtractedRequirement] = Field(default_factory=list)
    capability_assessments: List[CapabilityAssessment] = Field(default_factory=list)
    configuration_scope: List[str] = Field(default_factory=list)
    custom_development_scope: List[str] = Field(default_factory=list)
    unsupported_or_clarification_items: List[str] = Field(default_factory=list)
    deliverables: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    exclusions: List[str] = Field(default_factory=list)
    technical_risks: List[str] = Field(default_factory=list)
    items_requiring_human_review: List[str] = Field(default_factory=list)
    tasks: List[TaskEstimate] = Field(default_factory=list)
    total_estimated_hours: float = Field(default=0.0, ge=0.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ProposalDraft(BaseModel):
    """Client proposal document generated from structured scope."""
    proposal_id: str
    project_id: str
    scope_version: str
    title: str
    client_name: Optional[str] = "Client"
    executive_summary: str
    recommended_solution: str
    existing_capabilities_utilized: List[str] = Field(default_factory=list)
    proposed_configuration_work: List[str] = Field(default_factory=list)
    proposed_custom_development: List[str] = Field(default_factory=list)
    deliverables: List[str] = Field(default_factory=list)
    tasks_summary: List[Dict[str, Any]] = Field(default_factory=list)
    total_estimated_hours: float
    implementation_phases: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    exclusions: List[str] = Field(default_factory=list)
    risks_and_questions: List[str] = Field(default_factory=list)
    commercial_terms_placeholder: str = Field(
        default="Commercial rates and fixed milestone fees are to be finalized upon scope approval."
    )
    status: ProposalStatus = Field(default=ProposalStatus.DRAFT)
    reviewer_id: Optional[str] = None
    rejection_reason: Optional[str] = None
    approved_at: Optional[datetime] = None
    delivered_to_client: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ReviewDecisionRecord(BaseModel):
    """Persisted record of human review decisions."""
    decision_id: str
    project_id: str
    proposal_id: str
    scope_version: str
    action: ReviewAction
    reviewer_id: str
    comments: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class MeetingTranscriptRecord(BaseModel):
    """Persisted raw meeting transcript and metadata."""
    transcript_id: str
    project_id: str
    meeting_type: str = Field(default="initial", description="initial | follow_up")
    title: str
    client_name: Optional[str] = "Client"
    raw_text: str
    meeting_date: Optional[str] = None
    processed_at: datetime = Field(default_factory=datetime.utcnow)
    model_used: str = "claude-3-5-sonnet-20241022"
