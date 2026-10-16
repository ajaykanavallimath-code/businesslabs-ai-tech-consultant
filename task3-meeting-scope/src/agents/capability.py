"""
Agent 2: Capability Analyst.
Queries Task 1 Knowledge Brain to investigate whether requested features can be
fulfilled natively through Brilliant Directories settings, add-ons, or configuration
before recommending custom development. Preserves citations, evidence, and uncertainty.
"""

from typing import List, Dict, Optional
from ..models import (
    ExtractedRequirement,
    CapabilityAssessment,
    CapabilityStatus,
    RequirementStatus,
)
from ..kb_client import KnowledgeBrainClient
from ..config import settings


class CapabilityAnalyst:
    """Investigates client requirements against Brilliant Directories native capabilities."""

    def __init__(self, kb_client: Optional[KnowledgeBrainClient] = None):
        self.kb_client = kb_client or KnowledgeBrainClient()

    async def assess_requirements(
        self,
        requirements: List[ExtractedRequirement]
    ) -> List[CapabilityAssessment]:
        """
        Assess each requirement against Task 1 Knowledge Brain.
        Formulates a focused query, preserves citations and documentation evidence,
        and assigns an explainable capability status.
        """
        assessments: List[CapabilityAssessment] = []

        for req in requirements:
            # Skip assessment if requirement was explicitly removed
            if req.status == RequirementStatus.REMOVED:
                continue

            # Formulate focused capability inquiry
            inquiry_text = f"{req.title}. {req.description}"
            assessment = await self.kb_client.check_capability(
                requirement_id=req.id,
                requirement_text=inquiry_text
            )

            # Preserve requirement-level ambiguity flags
            if req.status == RequirementStatus.NEEDS_CLARIFICATION or req.is_conflicting:
                assessment.requires_expert_review = True
                if req.clarification_question:
                    if assessment.uncertainty_notes:
                        assessment.uncertainty_notes += f" | Client Clarification Needed: {req.clarification_question}"
                    else:
                        assessment.uncertainty_notes = f"Client Clarification Needed: {req.clarification_question}"

            assessments.append(assessment)

        return assessments

    def summarize_findings(self, assessments: List[CapabilityAssessment]) -> Dict[str, List[CapabilityAssessment]]:
        """Group assessments by capability status for clear scope structuring."""
        grouped: Dict[str, List[CapabilityAssessment]] = {
            "supported": [],
            "partially_supported": [],
            "unsupported": [],
            "uncertain": [],
            "needs_expert_review": [],
        }

        for ass in assessments:
            if ass.status == CapabilityStatus.SUPPORTED:
                grouped["supported"].append(ass)
            elif ass.status == CapabilityStatus.PARTIALLY_SUPPORTED:
                grouped["partially_supported"].append(ass)
            elif ass.status == CapabilityStatus.UNSUPPORTED:
                grouped["unsupported"].append(ass)
            elif ass.status == CapabilityStatus.UNCERTAIN:
                grouped["uncertain"].append(ass)

            if ass.requires_expert_review or ass.status == CapabilityStatus.NEEDS_EXPERT_REVIEW:
                grouped["needs_expert_review"].append(ass)

        return grouped
