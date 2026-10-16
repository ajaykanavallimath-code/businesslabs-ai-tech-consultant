"""
Agent 4: Proposal Writer.
Generates a professional client proposal draft from the validated Scope of Work.
Strictly maintains consistency with task estimates, evidence, assumptions, and exclusions.
Proposals start in 'draft' status and can never be delivered without explicit human approval.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime

from ..models import (
    ScopeOfWork,
    ProposalDraft,
    ProposalStatus,
    CapabilityStatus,
)


class ProposalWriter:
    """Generates professional, client-ready proposal drafts from structured scopes."""

    def generate_draft(
        self,
        scope: ScopeOfWork,
        client_name: str = "Client",
    ) -> ProposalDraft:
        """Construct the proposal draft matching the scope."""
        proposal_id = f"PRP-{scope.project_id}-{scope.version}"

        # Extract existing platform capabilities utilized
        existing_caps: List[str] = []
        for ass in scope.capability_assessments:
            if ass.status in (CapabilityStatus.SUPPORTED, CapabilityStatus.PARTIALLY_SUPPORTED):
                entry = f"{ass.native_feature_name or 'Native BD Feature'}: {ass.evidence_summary}"
                if ass.documentation_urls:
                    entry += f" (Reference: {ass.documentation_urls[0]})"
                existing_caps.append(entry)

        # Implementation phases
        phases = [
            "Phase 1: Discovery & Architecture Validation — Reviewing requirements and finalizing platform configuration pathways.",
            "Phase 2: Platform Configuration & Customization — Core directory settings, branding, membership tiers, and custom widgets.",
            "Phase 3: Integration & Quality Assurance — Testing payment flows, webhook integrations, and cross-browser user journeys.",
            "Phase 4: Client Review, UAT & Production Launch — User acceptance testing, domain DNS mapping, and administrative handover.",
        ]

        # Summarize tasks for proposal
        tasks_summary = [
            {
                "task_id": t.task_id,
                "title": t.title,
                "work_type": t.work_type.value,
                "estimated_hours": t.estimated_hours,
                "confidence": t.confidence.value,
                "dependencies": t.dependencies,
            }
            for t in scope.tasks
        ]

        # Risks and unresolved questions
        risks_and_questions: List[str] = list(scope.technical_risks)
        if scope.unsupported_or_clarification_items:
            risks_and_questions.append(
                "Items Awaiting Confirmation: " + "; ".join(scope.unsupported_or_clarification_items[:3])
            )

        executive_summary = (
            f"This proposal outlines the implementation plan for {scope.project_title}. "
            f"Our solution leverages native Brilliant Directories capabilities where supported to maximize "
            f"delivery speed and minimize maintenance costs, complemented by tailored development for unique client needs. "
            f"The estimated implementation effort is {scope.total_estimated_hours:.1f} hours across configured deliverables."
        )

        recommended_solution = (
            f"We recommend deploying a customized Brilliant Directories directory architecture. "
            f"Native platform settings will be utilized for directory structures, membership tiers, and payment processing, "
            f"while bespoke widgets and integrations bridge any specific client business rules."
        )

        return ProposalDraft(
            proposal_id=proposal_id,
            project_id=scope.project_id,
            scope_version=scope.version,
            title=f"Implementation Proposal: {scope.project_title}",
            client_name=client_name,
            executive_summary=executive_summary,
            recommended_solution=recommended_solution,
            existing_capabilities_utilized=existing_caps,
            proposed_configuration_work=scope.configuration_scope,
            proposed_custom_development=scope.custom_development_scope,
            deliverables=scope.deliverables,
            tasks_summary=tasks_summary,
            total_estimated_hours=scope.total_estimated_hours,
            implementation_phases=phases,
            assumptions=scope.assumptions,
            exclusions=scope.exclusions,
            risks_and_questions=risks_and_questions,
            commercial_terms_placeholder=(
                "Commercial rates, billing schedules, and fixed milestone disbursements "
                "will be agreed upon in the master services agreement following scope approval."
            ),
            status=ProposalStatus.DRAFT,
            reviewer_id=None,
            rejection_reason=None,
            approved_at=None,
            delivered_to_client=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
