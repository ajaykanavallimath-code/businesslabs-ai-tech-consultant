"""
Tests for domain models in Task 3: Meeting to Scope.
Verifies schema constraints, enums, hour validations, and default states.
"""

import pytest
from pydantic import ValidationError

from src.models import (
    ExtractedRequirement,
    RequirementType,
    RequirementCertainty,
    RequirementStatus,
    CapabilityAssessment,
    CapabilityStatus,
    TaskEstimate,
    WorkType,
    EstimateConfidence,
    ScopeOfWork,
    ProposalDraft,
    ProposalStatus,
    ChangeItem,
    ReviewAction,
)


def test_extracted_requirement_valid():
    """Verify valid ExtractedRequirement creation and evidence attachment."""
    req = ExtractedRequirement(
        id="REQ-001",
        title="Stripe Membership Payments",
        description="Automate monthly recurring billing via Stripe.",
        req_type=RequirementType.FUNCTIONAL,
        certainty=RequirementCertainty.EXPLICIT_FACT,
        status=RequirementStatus.CONFIRMED,
        transcript_evidence="We must have automated membership subscription tiers with Stripe.",
        user_roles=["Lawyer", "Admin"],
    )
    assert req.id == "REQ-001"
    assert req.certainty == RequirementCertainty.EXPLICIT_FACT
    assert "Stripe" in req.transcript_evidence


def test_task_estimate_non_negative_hours():
    """Verify task hour estimates must be non-negative (>= 0)."""
    valid_task = TaskEstimate(
        task_id="TSK-001",
        title="Payment Gateway Setup",
        description="Configure Stripe keys and webhook endpoints.",
        linked_requirement_ids=["REQ-001"],
        work_type=WorkType.CONFIGURATION,
        estimated_hours=4.5,
        estimation_rationale="Standard Stripe configuration effort.",
        confidence=EstimateConfidence.HIGH,
    )
    assert valid_task.estimated_hours == 4.5

    # Negative hours must raise ValidationError
    with pytest.raises(ValidationError):
        TaskEstimate(
            task_id="TSK-002",
            title="Invalid Task",
            description="Testing negative hours.",
            estimated_hours=-2.0,
            estimation_rationale="Invalid negative value.",
        )


def test_capability_assessment_enums_and_citations():
    """Verify CapabilityAssessment enum states and documentation citation handling."""
    assessment = CapabilityAssessment(
        requirement_id="REQ-001",
        status=CapabilityStatus.SUPPORTED,
        native_feature_name="Stripe Payment Gateway Integration",
        configuration_path="Finance > Payment Gateways > Stripe",
        documentation_urls=["https://support.brilliantdirectories.com/support/solutions/articles/12345"],
        evidence_summary="Supported natively with webhooks and recurring billing.",
        recommended_approach="configuration",
        requires_expert_review=False,
    )
    assert assessment.status == CapabilityStatus.SUPPORTED
    assert len(assessment.documentation_urls) == 1
    assert assessment.requires_expert_review is False


def test_proposal_draft_default_state():
    """Verify ProposalDraft defaults strictly to DRAFT and delivered_to_client = False."""
    proposal = ProposalDraft(
        proposal_id="PRP-001",
        project_id="PRJ-001",
        scope_version="v1.0",
        title="Implementation Proposal",
        executive_summary="Summary of work.",
        recommended_solution="Brilliant Directories configuration.",
        total_estimated_hours=24.0,
    )
    assert proposal.status == ProposalStatus.DRAFT
    assert proposal.delivered_to_client is False
    assert proposal.reviewer_id is None
    assert proposal.approved_at is None


def test_change_item_classification():
    """Verify ChangeItem supports valid change classifications and delta hours."""
    chg = ChangeItem(
        change_id="CHG-001",
        classification=RequirementStatus.MODIFIED,
        original_requirement_id="REQ-001",
        original_text="Stripe single currency",
        revised_text="Stripe multi-currency with invoice receipts",
        transcript_evidence="We now need multi-currency billing in USD, CAD, and GBP.",
        reason="Client expanded billing requirement to multi-currency.",
        hour_delta=3.5,
        human_approval_required=True,
    )
    assert chg.classification == RequirementStatus.MODIFIED
    assert chg.hour_delta == 3.5
    assert chg.human_approval_required is True
