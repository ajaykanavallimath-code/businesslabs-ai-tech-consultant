"""
Tests for Agent 3 (Scope Planner) and Agent 4 (Proposal Writer).
Verifies scope completeness, task-estimate math consistency, requirement linkage,
and proposal consistency with scope estimates.
"""

import pytest
from src.agents.planner import ScopePlanner
from src.agents.proposal import ProposalWriter
from src.models import (
    ExtractedRequirement,
    CapabilityAssessment,
    CapabilityStatus,
    RequirementStatus,
    WorkType,
    ProposalStatus,
)


@pytest.fixture
def sample_scope_inputs():
    reqs = [
        ExtractedRequirement(
            id="REQ-001",
            title="Branding & Design Setup",
            description="Configure directory theme, header logo, and colors.",
            transcript_evidence="Deep blue and gold scheme.",
        ),
        ExtractedRequirement(
            id="REQ-002",
            title="Stripe Membership Tiers",
            description="Automate lawyer subscription plans.",
            transcript_evidence="Automated subscription tiers with Stripe.",
        ),
        ExtractedRequirement(
            id="REQ-003",
            title="Custom Webhook Integration",
            description="Zapier webhook lead capture.",
            transcript_evidence="Zapier lead capture.",
            req_type="custom_development",
        ),
    ]

    assessments = [
        CapabilityAssessment(
            requirement_id="REQ-001",
            status=CapabilityStatus.SUPPORTED,
            native_feature_name="Design Settings",
            evidence_summary="Supported natively in Admin Settings.",
        ),
        CapabilityAssessment(
            requirement_id="REQ-002",
            status=CapabilityStatus.SUPPORTED,
            native_feature_name="Stripe Gateway",
            evidence_summary="Supported natively in Finance Settings.",
        ),
        CapabilityAssessment(
            requirement_id="REQ-003",
            status=CapabilityStatus.UNSUPPORTED,
            evidence_summary="Requires custom webhook script development.",
            recommended_approach="custom_development",
        ),
    ]

    analysis_data = {
        "client_objectives": ["Automate attorney membership subscriptions."],
        "current_workflow": "Managing attorneys on Google Sheets.",
        "assumptions": ["Client provides Stripe credentials."],
        "exclusions": ["External server hosting."],
        "risks": ["Stripe API key delays."],
    }

    return reqs, assessments, analysis_data


def test_scope_planner_hours_math_and_linkage(sample_scope_inputs):
    """Verify total estimated hours strictly equals bottom-up sum of tasks and requirements are linked."""
    reqs, assessments, analysis_data = sample_scope_inputs
    planner = ScopePlanner()

    scope = planner.build_scope(
        project_id="PRJ-TEST-01",
        project_title="Test Directory Scope",
        requirements=reqs,
        assessments=assessments,
        analysis_data=analysis_data,
        version="v1.0",
    )

    # 1. Total hours must equal sum of individual task hours
    calculated_sum = round(sum(t.estimated_hours for t in scope.tasks), 2)
    assert scope.total_estimated_hours == calculated_sum
    assert scope.total_estimated_hours > 0

    # 2. Every task has >= 0 hours
    for task in scope.tasks:
        assert task.estimated_hours >= 0.0
        assert len(task.linked_requirement_ids) > 0
        assert task.estimation_rationale != ""

    # 3. Scope categories are populated
    assert len(scope.configuration_scope) >= 2
    assert len(scope.custom_development_scope) >= 1
    assert len(scope.deliverables) > 0


def test_proposal_writer_consistency_with_scope(sample_scope_inputs):
    """Verify ProposalDraft matches scope total hours, deliverables, and defaults to DRAFT."""
    reqs, assessments, analysis_data = sample_scope_inputs
    planner = ScopePlanner()
    scope = planner.build_scope(
        project_id="PRJ-TEST-01",
        project_title="Test Directory Scope",
        requirements=reqs,
        assessments=assessments,
        analysis_data=analysis_data,
    )

    writer = ProposalWriter()
    proposal = writer.generate_draft(scope=scope, client_name="Acme Legal")

    # Proposal hours must strictly equal scope hours
    assert proposal.total_estimated_hours == scope.total_estimated_hours
    assert proposal.status == ProposalStatus.DRAFT
    assert proposal.delivered_to_client is False
    assert proposal.project_id == scope.project_id
    assert proposal.scope_version == scope.version
    assert len(proposal.deliverables) == len(scope.deliverables)
    assert len(proposal.tasks_summary) == len(scope.tasks)
