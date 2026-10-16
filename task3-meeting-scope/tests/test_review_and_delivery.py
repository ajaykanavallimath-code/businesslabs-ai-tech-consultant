"""
Tests for Human Review Service and Proposal Delivery Gates.
Verifies approval/rejection state transitions, audit logging, and hard delivery security gates:
NO UNAPPROVED OR SUPERSEDED PROPOSALS CAN BE DELIVERED TO CLIENTS.
"""

import pytest
from src.models import ProposalDraft, ProposalStatus, ScopeOfWork
from src.review_service import ReviewService
from src.storage import Task3Storage


@pytest.fixture
def review_setup(test_storage):
    scope = ScopeOfWork(
        scope_id="SCP-REV-v1.0",
        project_id="PRJ-REV-01",
        version="v1.0",
        project_title="Review Test Project",
        total_estimated_hours=20.0,
    )
    test_storage.save_scope(scope)

    proposal = ProposalDraft(
        proposal_id="PRP-REV-v1.0",
        project_id="PRJ-REV-01",
        scope_version="v1.0",
        title="Review Test Proposal",
        executive_summary="Summary",
        recommended_solution="Solution",
        total_estimated_hours=20.0,
        status=ProposalStatus.DRAFT,
    )
    test_storage.save_proposal(proposal)

    service = ReviewService(storage=test_storage)
    return service, proposal, scope


def test_approve_proposal_flow(review_setup):
    """Verify approval transition updates status, timestamps, and persists decision record."""
    service, proposal, _ = review_setup

    approved = service.approve_proposal(
        proposal_id=proposal.proposal_id,
        reviewer_id="Lead Consultant John",
        comments="Scope validated against client budget.",
    )

    assert approved.status == ProposalStatus.APPROVED
    assert approved.reviewer_id == "Lead Consultant John"
    assert approved.approved_at is not None

    # Verify decision logged
    decisions = service.storage.list_review_decisions(proposal.project_id)
    assert len(decisions) == 1
    assert decisions[0].action == "approve"
    assert decisions[0].reviewer_id == "Lead Consultant John"


def test_reject_proposal_flow(review_setup):
    """Verify rejection transition requires mandatory reason and logs decision."""
    service, proposal, _ = review_setup

    rejected = service.reject_proposal(
        proposal_id=proposal.proposal_id,
        reviewer_id="Technical Director",
        rejection_reason="Estimated hours too low for custom webhook scope.",
    )

    assert rejected.status == ProposalStatus.REJECTED
    assert rejected.rejection_reason == "Estimated hours too low for custom webhook scope."
    assert rejected.delivered_to_client is False


def test_delivery_gate_blocks_unapproved_draft(review_setup):
    """CRITICAL SECURITY GATE: Attempting to deliver unapproved draft raises PermissionError."""
    service, proposal, _ = review_setup

    assert proposal.status == ProposalStatus.DRAFT

    with pytest.raises(PermissionError, match="No proposal may be delivered to a client without explicit human approval"):
        service.deliver_proposal(
            proposal_id=proposal.proposal_id,
            recipient_email="client@example.com",
            delivered_by="Account Manager",
        )


def test_delivery_gate_blocks_rejected_draft(review_setup):
    """CRITICAL SECURITY GATE: Attempting to deliver rejected proposal raises PermissionError."""
    service, proposal, _ = review_setup
    service.reject_proposal(proposal.proposal_id, "Reviewer", "Scope rejected")

    with pytest.raises(PermissionError, match="No proposal may be delivered"):
        service.deliver_proposal(
            proposal_id=proposal.proposal_id,
            recipient_email="client@example.com",
            delivered_by="Account Manager",
        )


def test_delivery_gate_blocks_superseded_version(review_setup):
    """CRITICAL SECURITY GATE: Attempting to deliver superseded proposal raises PermissionError."""
    service, proposal, _ = review_setup
    proposal.status = ProposalStatus.SUPERSEDED
    service.storage.save_proposal(proposal)

    with pytest.raises(PermissionError, match="superseded"):
        service.deliver_proposal(
            proposal_id=proposal.proposal_id,
            recipient_email="client@example.com",
            delivered_by="Account Manager",
        )


def test_delivery_succeeds_only_after_explicit_approval(review_setup):
    """Verify delivery succeeds once the proposal is explicitly approved."""
    service, proposal, _ = review_setup

    service.approve_proposal(proposal.proposal_id, "Lead Consultant", "Approved for presentation.")

    delivery_res = service.deliver_proposal(
        proposal_id=proposal.proposal_id,
        recipient_email="client@example.com",
        delivered_by="Account Manager",
    )

    assert delivery_res["success"] is True
    assert delivery_res["delivered_to"] == "client@example.com"
    stored_prop = service.storage.get_proposal(proposal.proposal_id)
    assert stored_prop.delivered_to_client is True


def test_material_edit_resets_approved_proposal_to_draft(review_setup):
    """CRITICAL GATE: Editing an approved proposal resets status to DRAFT and requires renewed approval."""
    service, proposal, _ = review_setup
    service.approve_proposal(proposal.proposal_id, "Reviewer 1", "Approved")

    # Manually edit content
    edited = service.edit_proposal_content(
        proposal_id=proposal.proposal_id,
        reviewer_id="Reviewer 2",
        executive_summary="Updated scope summary with revised timeline.",
    )

    assert edited.status == ProposalStatus.DRAFT
    assert edited.approved_at is None
    assert edited.delivered_to_client is False

    # Delivery must be blocked again until re-approved
    with pytest.raises(PermissionError):
        service.deliver_proposal(
            proposal_id=proposal.proposal_id,
            recipient_email="client@example.com",
            delivered_by="Account Manager",
        )
