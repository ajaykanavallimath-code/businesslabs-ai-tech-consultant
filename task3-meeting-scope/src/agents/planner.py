"""
Agent 3: Scope Planner.
Constructs a structured Software Implementation Scope of Work and bottom-up Task Breakdown.
Separates native configuration from custom development, assigns realistic hour estimates,
identifies task dependencies, and flags provisional or uncertain items.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime

from ..models import (
    ExtractedRequirement,
    CapabilityAssessment,
    CapabilityStatus,
    TaskEstimate,
    ScopeOfWork,
    WorkType,
    EstimateConfidence,
    RequirementStatus,
)


class ScopePlanner:
    """Builds structured scope and bottom-up task hour estimates."""

    def build_scope(
        self,
        project_id: str,
        project_title: str,
        requirements: List[ExtractedRequirement],
        assessments: List[CapabilityAssessment],
        analysis_data: Dict[str, Any],
        version: str = "v1.0",
    ) -> ScopeOfWork:
        """Construct the complete Scope of Work."""
        scope_id = f"SCP-{project_id}-{version}"

        # Build requirement lookup
        assessment_by_req: Dict[str, CapabilityAssessment] = {
            a.requirement_id: a for a in assessments
        }

        configuration_scope: List[str] = []
        custom_dev_scope: List[str] = []
        unsupported_items: List[str] = []
        review_items: List[str] = []

        for req in requirements:
            ass = assessment_by_req.get(req.id)
            status = ass.status if ass else CapabilityStatus.UNCERTAIN

            if status == CapabilityStatus.SUPPORTED:
                feature_desc = f"{req.title}: Configure via native BD feature '{ass.native_feature_name or 'Standard Setting'}' ({ass.configuration_path or 'Admin Dashboard'})."
                configuration_scope.append(feature_desc)
            elif status == CapabilityStatus.PARTIALLY_SUPPORTED:
                feature_desc = f"{req.title}: Native BD foundation with minor configuration adjustments ({ass.native_feature_name or 'Add-on'})."
                configuration_scope.append(feature_desc)
            elif status == CapabilityStatus.UNSUPPORTED:
                dev_desc = f"{req.title}: Custom development required. BD does not support natively ({ass.evidence_summary})."
                custom_dev_scope.append(dev_desc)
            else:
                unsupported_items.append(f"{req.title}: Capability uncertain or awaiting client clarification ({req.clarification_question or 'Under investigation'}).")

            if (ass and ass.requires_expert_review) or req.is_conflicting or req.status == RequirementStatus.NEEDS_CLARIFICATION:
                review_items.append(f"{req.id} ({req.title}): {ass.uncertainty_notes if ass else 'Requires clarification'}")

        # Deliverables list
        deliverables: List[str] = [
            "Configured and branded Brilliant Directories portal.",
            "Configured membership plans, pricing rules, and payment gateway integration.",
            "Directory category structure, custom fields, and search filter setup.",
        ]
        if custom_dev_scope:
            deliverables.append("Custom widget implementations and external webhook integrations.")
        deliverables.extend([
            "User Acceptance Testing (UAT) verification checklist and sign-off report.",
            "Administrator handover training and system configuration documentation.",
        ])

        # Generate Task Breakdown
        tasks = self._generate_tasks(requirements, assessment_by_req)

        # Bottom-up total hours calculation
        total_hours = round(sum(t.estimated_hours for t in tasks), 2)

        return ScopeOfWork(
            scope_id=scope_id,
            project_id=project_id,
            version=version,
            project_title=project_title,
            client_objectives=analysis_data.get("client_objectives", []),
            current_workflow_summary=analysis_data.get("current_workflow", "Current workflow under review."),
            requirements=requirements,
            capability_assessments=assessments,
            configuration_scope=configuration_scope,
            custom_development_scope=custom_dev_scope,
            unsupported_or_clarification_items=unsupported_items,
            deliverables=deliverables,
            assumptions=analysis_data.get("assumptions", []),
            exclusions=analysis_data.get("exclusions", []),
            technical_risks=analysis_data.get("risks", []),
            items_requiring_human_review=review_items,
            tasks=tasks,
            total_estimated_hours=total_hours,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

    def _generate_tasks(
        self,
        requirements: List[ExtractedRequirement],
        assessments: Dict[str, CapabilityAssessment]
    ) -> List[TaskEstimate]:
        """Generate structured tasks with bottom-up hour estimates and dependencies."""
        tasks: List[TaskEstimate] = []
        task_idx = 1

        # Phase 1: Environment & Foundation
        setup_task = TaskEstimate(
            task_id=f"TSK-{task_idx:03d}",
            title="Initial Portal Setup & Brand Styling",
            description="Configure directory basic settings, domain mapping, brand logos, primary color scheme, and typography.",
            linked_requirement_ids=[r.id for r in requirements if "branding" in r.title.lower() or "portal" in r.title.lower()] or ["REQ-001"],
            work_type=WorkType.CONFIGURATION,
            estimated_hours=4.0,
            estimation_rationale="Standard baseline BD platform branding and setup based on historical projects.",
            confidence=EstimateConfidence.HIGH,
            confidence_score=0.95,
            dependencies=[],
            acceptance_criteria=[
                "Site loads under configured test domain.",
                "Client branding, logo, and color palette applied to global layout."
            ],
            is_provisional=False,
        )
        tasks.append(setup_task)
        task_idx += 1

        # Phase 2: Requirement-driven tasks
        for req in requirements:
            if req.status == RequirementStatus.REMOVED:
                continue

            ass = assessments.get(req.id)
            is_prov = req.status == RequirementStatus.NEEDS_CLARIFICATION or req.certainty == "unconfirmed"

            # Determine confidence and numeric confidence_score
            if is_prov:
                conf = EstimateConfidence.PROVISIONAL
                score = 0.40
            elif ass and ass.confidence is not None:
                score = float(ass.confidence)
                conf = EstimateConfidence.HIGH if score >= 0.80 else (
                    EstimateConfidence.MEDIUM if score >= 0.60 else EstimateConfidence.LOW
                )
            elif ass and ass.status == CapabilityStatus.SUPPORTED:
                conf = EstimateConfidence.HIGH
                score = 0.90
            elif ass and ass.status == CapabilityStatus.PARTIALLY_SUPPORTED:
                conf = EstimateConfidence.MEDIUM
                score = 0.75
            elif ass and ass.status == CapabilityStatus.UNSUPPORTED:
                conf = EstimateConfidence.MEDIUM
                score = 0.65
            else:
                conf = EstimateConfidence.MEDIUM
                score = 0.60

            # Determine task work type and hours
            if ass and ass.status == CapabilityStatus.SUPPORTED:
                work_type = WorkType.CONFIGURATION
                hours = 3.5
                rationale = f"Native Brilliant Directories configuration: {ass.native_feature_name}. Admin setting implementation."
                ac = [
                    f"Feature '{ass.native_feature_name}' successfully enabled in {ass.configuration_path}.",
                    "Verified operational from frontend member view."
                ]
            elif ass and ass.status == CapabilityStatus.PARTIALLY_SUPPORTED:
                work_type = WorkType.CONFIGURATION
                hours = 5.0
                rationale = f"Native feature '{ass.native_feature_name}' configured with minor CSS/field customizations."
                ac = ["Configuration settings saved and custom display adjustments verified."]
            elif ass and ass.status == CapabilityStatus.UNSUPPORTED:
                work_type = WorkType.CUSTOM_DEVELOPMENT
                hours = 14.0
                rationale = "Custom frontend widget and webhook integration development; unsupported natively by platform."
                ac = [
                    "Custom widget developed, tested in staging, and embedded.",
                    "Webhook payloads successfully received and validated."
                ]
            else:
                work_type = WorkType.INTEGRATION
                hours = 6.0
                rationale = "Provisional estimate pending client clarification and technical feasibility verification."
                ac = ["Clarification resolved with client and integration pathway validated."]

            task = TaskEstimate(
                task_id=f"TSK-{task_idx:03d}",
                title=f"Implement {req.title}",
                description=f"Implement functionality for requirement {req.id}: {req.description}",
                linked_requirement_ids=[req.id],
                work_type=work_type,
                estimated_hours=hours,
                estimation_rationale=rationale,
                confidence=conf,
                confidence_score=score,
                dependencies=["TSK-001"],
                acceptance_criteria=ac,
                is_provisional=is_prov,
            )
            tasks.append(task)
            task_idx += 1

        # Phase 3: Testing & Handover
        prev_task_ids = [t.task_id for t in tasks if t.task_id != "TSK-001"]
        uat_task = TaskEstimate(
            task_id=f"TSK-{task_idx:03d}",
            title="User Acceptance Testing (UAT) & QA Verification",
            description="Execute end-to-end functional test cases across member registration, search, and custom workflows.",
            linked_requirement_ids=[r.id for r in requirements],
            work_type=WorkType.TESTING,
            estimated_hours=6.0,
            estimation_rationale="Comprehensive test verification covering all configured settings and custom widgets.",
            confidence=EstimateConfidence.HIGH,
            confidence_score=0.90,
            dependencies=prev_task_ids[:4],
            acceptance_criteria=[
                "All test cases executed and documented.",
                "Zero blocking or critical defects reported."
            ],
            is_provisional=False,
        )
        tasks.append(uat_task)
        task_idx += 1

        deploy_task = TaskEstimate(
            task_id=f"TSK-{task_idx:03d}",
            title="Production Deployment & Client Handover",
            description="DNS cutover, SSL verification, production admin configuration, and recorded administrator walkthrough.",
            linked_requirement_ids=[r.id for r in requirements],
            work_type=WorkType.DEPLOYMENT,
            estimated_hours=4.0,
            estimation_rationale="Production go-live cutover and client training session.",
            confidence=EstimateConfidence.HIGH,
            confidence_score=0.95,
            dependencies=[uat_task.task_id],
            acceptance_criteria=[
                "Live domain serving over HTTPS.",
                "Admin training session completed and handover recording delivered."
            ],
            is_provisional=False,
        )
        tasks.append(deploy_task)

        return tasks
