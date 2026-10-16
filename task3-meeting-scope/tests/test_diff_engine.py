"""
Tests for Agent 5 / Diff Engine.
Verifies change detection classifications, hour delta math, version preservation,
and out-of-scope request separation.
"""

import pytest
from src.agents.diff_engine import DiffEngine
from src.agents.planner import ScopePlanner
from src.models import (
    ExtractedRequirement,
    CapabilityAssessment,
    CapabilityStatus,
    RequirementStatus,
    RequirementCertainty,
)


@pytest.fixture
def baseline_scope():
    planner = ScopePlanner()
    reqs = [
        ExtractedRequirement(
            id="REQ-001",
            title="Branding & Design Setup",
            description="Theme and logo setup.",
            transcript_evidence="Blue and gold.",
        ),
        ExtractedRequirement(
            id="REQ-002",
            title="Stripe Membership Billing",
            description="Charge $49/mo in USD.",
            transcript_evidence="Stripe monthly billing.",
        ),
        ExtractedRequirement(
            id="REQ-003",
            title="Attorney Client Reviews",
            description="Public star ratings and admin review approval.",
            transcript_evidence="5-star ratings and admin approval.",
            status=RequirementStatus.CONFIRMED,
        ),
    ]
    assessments = [
        CapabilityAssessment(
            requirement_id="REQ-001",
            status=CapabilityStatus.SUPPORTED,
            evidence_summary="Supported natively.",
        ),
        CapabilityAssessment(
            requirement_id="REQ-002",
            status=CapabilityStatus.SUPPORTED,
            evidence_summary="Supported natively.",
        ),
        CapabilityAssessment(
            requirement_id="REQ-003",
            status=CapabilityStatus.SUPPORTED,
            evidence_summary="Supported natively.",
        ),
    ]
    analysis = {
        "client_objectives": ["Launch legal portal."],
        "assumptions": ["Active BD license."],
        "exclusions": ["Custom servers."],
        "risks": ["DNS delays."],
    }
    return planner.build_scope(
        project_id="PRJ-DIFF-01",
        project_title="Baseline Scope",
        requirements=reqs,
        assessments=assessments,
        analysis_data=analysis,
        version="v1.0",
    )


def test_diff_engine_detects_all_change_types(baseline_scope):
    """Verify DiffEngine accurately classifies modified, added, removed, and out-of-scope items."""
    diff_engine = DiffEngine()

    followup_reqs = [
        # 1. Modified: Stripe billing now needs multi-currency and custom invoices
        ExtractedRequirement(
            id="REQ-002",
            title="Stripe Membership Billing",
            description="Multi-currency billing in USD, CAD, GBP with custom PDF invoice generation.",
            transcript_evidence="Multi-currency billing in USD, CAD, and GBP.",
        ),
        # 2. Removed: Cancel attorney reviews
        ExtractedRequirement(
            id="REQ-003",
            title="Attorney Client Reviews",
            description="Cancel and drop member reviews for phase 1 launch.",
            transcript_evidence="Cancel member reviews for phase 1.",
        ),
        # 3. Added: Zapier lead capture webhook
        ExtractedRequirement(
            id="REQ-004",
            title="Zapier Webhook Lead Capture",
            description="Pipe new attorney registrations to Zapier and HubSpot.",
            transcript_evidence="Piped immediately to CRM via Zapier.",
        ),
        # 4. Out of Scope: Native mobile application
        ExtractedRequirement(
            id="REQ-005",
            title="Native iOS and Android Mobile App",
            description="Publish native downloadable app on Apple App Store.",
            transcript_evidence="Native mobile app published on App Store.",
        ),
    ]

    followup_ass = [
        CapabilityAssessment(
            requirement_id="REQ-004",
            status=CapabilityStatus.UNSUPPORTED,
            evidence_summary="Requires custom webhook script development.",
        )
    ]

    report, rev_scope, rev_proposal = diff_engine.detect_changes(
        baseline_scope=baseline_scope,
        followup_requirements=followup_reqs,
        followup_assessments=followup_ass,
        followup_analysis_data={"client_objectives": ["Expanded scope."], "risks": [], "assumptions": [], "exclusions": []},
        new_version="v2.0",
    )

    # 1. Verify classifications
    classifications = {c.classification for c in report.changes}
    assert RequirementStatus.MODIFIED in classifications
    assert RequirementStatus.REMOVED in classifications
    assert RequirementStatus.ADDED in classifications
    assert RequirementStatus.OUT_OF_SCOPE in classifications

    # 2. Verify out of scope items segregated
    assert len(report.out_of_scope_requests) == 1
    assert "mobile" in report.out_of_scope_requests[0].reason.lower()

    # 3. Verify hour delta math
    expected_delta = round(rev_scope.total_estimated_hours - baseline_scope.total_estimated_hours, 2)
    assert report.net_hour_delta == expected_delta
    assert report.total_original_hours == baseline_scope.total_estimated_hours
    assert report.total_revised_hours == rev_scope.total_estimated_hours

    # 4. Verify baseline scope was preserved and unmodified
    assert baseline_scope.version == "v1.0"
    assert rev_scope.version == "v2.0"
    assert rev_proposal.scope_version == "v2.0"
