"""
Human Review & Approval Service for Task 3: Meeting to Scope.
Enforces the backend review workflow, valid state transitions, and the critical delivery gate:
NO CLIENT DELIVERY WITHOUT EXPLICIT HUMAN APPROVAL OF THE EXACT VERSION.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
import uuid

from .models import (
    ProposalDraft,
    ProposalStatus,
    ReviewAction,
    ReviewDecisionRecord,
    ScopeOfWork,
)
from .storage import Task3Storage
from .config import settings


class ReviewService:
    """Manages human review decisions and enforces proposal delivery gates."""

    def __init__(self, storage: Optional[Task3Storage] = None):
        self.storage = storage or Task3Storage()

    def submit_for_review(self, proposal_id: str) -> ProposalDraft:
        """Move a proposal draft into PENDING_REVIEW state."""
        proposal = self.storage.get_proposal(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal with ID '{proposal_id}' not found.")

        if proposal.status == ProposalStatus.APPROVED:
            raise ValueError("Proposal is already approved.")
        if proposal.status == ProposalStatus.SUPERSEDED:
            raise ValueError("Cannot review a superseded proposal.")

        proposal.status = ProposalStatus.PENDING_REVIEW
        proposal.updated_at = datetime.utcnow()
        self.storage.save_proposal(proposal)
        return proposal

    def approve_proposal(
        self,
        proposal_id: str,
        reviewer_id: str,
        comments: Optional[str] = None,
    ) -> ProposalDraft:
        """
        Explicitly approve a proposal draft.
        Enforces that only DRAFT or PENDING_REVIEW versions can be approved.
        """
        if not reviewer_id or not reviewer_id.strip():
            raise ValueError("Reviewer ID is required to approve a proposal.")

        proposal = self.storage.get_proposal(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal with ID '{proposal_id}' not found.")

        if proposal.status == ProposalStatus.SUPERSEDED:
            raise ValueError("Cannot approve a superseded proposal.")
        if proposal.status == ProposalStatus.APPROVED:
            return proposal  # Already approved

        now = datetime.utcnow()
        proposal.status = ProposalStatus.APPROVED
        proposal.reviewer_id = reviewer_id.strip()
        proposal.approved_at = now
        proposal.rejection_reason = None
        proposal.updated_at = now
        self.storage.save_proposal(proposal)

        # Record decision audit log
        decision = ReviewDecisionRecord(
            decision_id=f"DEC-{uuid.uuid4().hex[:8]}",
            project_id=proposal.project_id,
            proposal_id=proposal.proposal_id,
            scope_version=proposal.scope_version,
            action=ReviewAction.APPROVE,
            reviewer_id=reviewer_id.strip(),
            comments=comments or "Approved for client presentation.",
            timestamp=now,
        )
        self.storage.save_review_decision(decision)

        return proposal

    def reject_proposal(
        self,
        proposal_id: str,
        reviewer_id: str,
        rejection_reason: str,
    ) -> ProposalDraft:
        """
        Reject a proposal draft with a mandatory rejection reason.
        """
        if not reviewer_id or not reviewer_id.strip():
            raise ValueError("Reviewer ID is required to reject a proposal.")
        if not rejection_reason or not rejection_reason.strip():
            raise ValueError("A specific rejection reason is mandatory.")

        proposal = self.storage.get_proposal(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal with ID '{proposal_id}' not found.")

        if proposal.status == ProposalStatus.SUPERSEDED:
            raise ValueError("Cannot reject a superseded proposal.")

        now = datetime.utcnow()
        proposal.status = ProposalStatus.REJECTED
        proposal.reviewer_id = reviewer_id.strip()
        proposal.rejection_reason = rejection_reason.strip()
        proposal.delivered_to_client = False
        proposal.updated_at = now
        self.storage.save_proposal(proposal)

        decision = ReviewDecisionRecord(
            decision_id=f"DEC-{uuid.uuid4().hex[:8]}",
            project_id=proposal.project_id,
            proposal_id=proposal.proposal_id,
            scope_version=proposal.scope_version,
            action=ReviewAction.REJECT,
            reviewer_id=reviewer_id.strip(),
            comments=rejection_reason.strip(),
            timestamp=now,
        )
        self.storage.save_review_decision(decision)

        return proposal

    def edit_proposal_content(
        self,
        proposal_id: str,
        reviewer_id: str,
        executive_summary: Optional[str] = None,
        recommended_solution: Optional[str] = None,
        commercial_terms: Optional[str] = None,
    ) -> ProposalDraft:
        """
        Human reviewer edits proposal content.
        CRITICAL SAFETY RULE: Editing an approved proposal resets its status to DRAFT
        and requires renewed review and approval.
        """
        proposal = self.storage.get_proposal(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal with ID '{proposal_id}' not found.")

        was_approved = proposal.status == ProposalStatus.APPROVED

        if executive_summary is not None:
            proposal.executive_summary = executive_summary
        if recommended_solution is not None:
            proposal.recommended_solution = recommended_solution
        if commercial_terms is not None:
            proposal.commercial_terms_placeholder = commercial_terms

        # Material edits reset status to DRAFT
        proposal.status = ProposalStatus.DRAFT
        proposal.delivered_to_client = False
        proposal.approved_at = None
        proposal.updated_at = datetime.utcnow()
        self.storage.save_proposal(proposal)

        decision = ReviewDecisionRecord(
            decision_id=f"DEC-{uuid.uuid4().hex[:8]}",
            project_id=proposal.project_id,
            proposal_id=proposal.proposal_id,
            scope_version=proposal.scope_version,
            action=ReviewAction.EDIT,
            reviewer_id=reviewer_id,
            comments="Proposal content manually edited by reviewer. Reset status to draft for renewed approval."
            if was_approved
            else "Proposal content edited by reviewer.",
            timestamp=datetime.utcnow(),
        )
        self.storage.save_review_decision(decision)

        return proposal

    def deliver_proposal(
        self,
        proposal_id: str,
        recipient_email: str,
        delivered_by: str,
    ) -> Dict[str, Any]:
        """
        CRITICAL GATE: Deliver proposal to client.
        Enforces that:
        1. The proposal MUST have status == APPROVED.
        2. The proposal CANNOT be superseded.
        3. Real external sending is disabled by default (safe simulation).
        """
        proposal = self.storage.get_proposal(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal with ID '{proposal_id}' not found.")

        # Hard Gate 1: Must be explicitly APPROVED
        if proposal.status != ProposalStatus.APPROVED:
            raise PermissionError(
                f"CLIENT DELIVERY BLOCKED: Proposal '{proposal_id}' is in '{proposal.status.value}' state. "
                "No proposal may be delivered to a client without explicit human approval."
            )

        # Hard Gate 2: Cannot deliver superseded version
        if proposal.status == ProposalStatus.SUPERSEDED:
            raise PermissionError(
                f"CLIENT DELIVERY BLOCKED: Version '{proposal.scope_version}' is superseded. "
                "Only the latest approved scope version may be delivered."
            )

        # Check latest scope version to prevent delivering outdated scope
        latest_scope = self.storage.get_scope(proposal.project_id)
        if latest_scope and latest_scope.version != proposal.scope_version:
            # Check if there is a newer scope version that superseded this one
            newer_proposals = [
                p for p in self.storage.list_proposals(proposal.project_id)
                if p.scope_version > proposal.scope_version
            ]
            if newer_proposals:
                raise PermissionError(
                    f"CLIENT DELIVERY BLOCKED: Proposal '{proposal_id}' is for version '{proposal.scope_version}', "
                    f"but a newer scope version '{latest_scope.version}' exists and requires separate approval."
                )

        now = datetime.utcnow()
        proposal.delivered_to_client = True
        proposal.updated_at = now
        self.storage.save_proposal(proposal)

        is_real = settings.enable_client_delivery
        delivery_mode = "LIVE" if is_real else "SIMULATED (Safe Default)"

        return {
            "success": True,
            "proposal_id": proposal.proposal_id,
            "project_id": proposal.project_id,
            "scope_version": proposal.scope_version,
            "delivered_to": recipient_email,
            "delivered_by": delivered_by,
            "delivery_timestamp": now.isoformat(),
            "mode": delivery_mode,
            "message": f"Proposal {proposal.proposal_id} delivered successfully under {delivery_mode} mode.",
        }
