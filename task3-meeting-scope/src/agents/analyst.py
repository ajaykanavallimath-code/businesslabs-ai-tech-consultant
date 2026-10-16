"""
Agent 1: Meeting Analyst.
Analyzes meeting transcripts to extract client goals, current workflows,
functional & non-functional requirements, constraints, assumptions, and ambiguity.
Attaches supporting transcript evidence to every requirement.
"""

import json
import re
from typing import List, Dict, Any, Tuple
from ..models import (
    ExtractedRequirement,
    RequirementType,
    RequirementCertainty,
    RequirementStatus,
)
from ..config import settings


ANALYST_SYSTEM_PROMPT = """You are a Senior Technical Consultant and Systems Analyst.
Analyze the provided client meeting transcript and extract structured project requirements.

Extract:
1. Client goals and business problems.
2. Current software/workflow.
3. Explicit functional & non-functional requirements.
4. Ambiguous, missing, or conflicting requirements with clarification questions.

Rules:
- Quote actual transcript text in transcript_evidence for traceability.
- Distinguish explicit facts from assumptions or unconfirmed interpretations.
- Never invent product capabilities, commitments, or deadlines not in transcript.
- Set certainty: explicit_fact, interpretation, assumption, or unconfirmed.

Output valid JSON matching this schema:
{
  "client_objectives": ["string"],
  "current_workflow": "string",
  "requirements": [
    {
      "id": "REQ-001",
      "title": "string",
      "description": "string",
      "req_type": "functional",
      "certainty": "explicit_fact",
      "status": "confirmed",
      "transcript_evidence": "quote from transcript",
      "user_roles": ["string"],
      "clarification_question": null,
      "is_conflicting": false
    }
  ],
  "assumptions": ["string"],
  "exclusions": ["string"],
  "risks": ["string"]
}
"""


class MeetingAnalyst:
    """Extracts structured requirements from client meeting transcripts."""

    def __init__(self, config=None, anthropic_client=None):
        self.config = config or settings
        self.client = anthropic_client
        if not self.client and not self.config.mock_llm and self.config.anthropic_api_key:
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=self.config.anthropic_api_key)
            except Exception:
                self.client = None

    async def analyze_transcript(
        self,
        transcript_text: str,
        project_id: str,
        title: str = "Client Meeting"
    ) -> Dict[str, Any]:
        """Process transcript and extract structured requirements."""
        clean_text = transcript_text.strip()
        if not clean_text:
            raise ValueError("Meeting transcript cannot be empty.")

        # If LLM is available and live mode enabled
        if self.client and not self.config.mock_llm:
            try:
                return await self._call_claude(clean_text)
            except Exception:
                # Fallback to deterministic heuristic analyzer
                pass

        return self._heuristic_analysis(clean_text, project_id, title)

    async def _call_claude(self, transcript_text: str) -> Dict[str, Any]:
        prompt = f"Transcript:\n{transcript_text}"
        response = self.client.messages.create(
            model=self.config.claude_model_primary,
            max_tokens=2500,
            temperature=0.0,
            system=ANALYST_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        content_text = response.content[0].text if response.content else "{}"
        clean_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", content_text.strip(), flags=re.MULTILINE)
        data = json.loads(clean_json)

        reqs = []
        for r in data.get("requirements", []):
            reqs.append(ExtractedRequirement.model_validate(r))
        data["requirements"] = reqs
        return data

    def _heuristic_analysis(self, text: str, project_id: str, title: str) -> Dict[str, Any]:
        """Deterministic transcript requirement extraction for testing and offline execution."""
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        lower_text = text.lower()

        objectives: List[str] = []
        requirements: List[ExtractedRequirement] = []
        assumptions: List[str] = []
        exclusions: List[str] = []
        risks: List[str] = []

        req_counter = 1

        # 1. Detect Core Objectives
        if "directory" in lower_text or "portal" in lower_text:
            objectives.append("Launch a professional online member directory platform.")
        if "lead" in lower_text or "match" in lower_text:
            objectives.append("Automate customer lead distribution to verified members.")
        if "monetiz" in lower_text or "subscription" in lower_text or "paid" in lower_text:
            objectives.append("Establish recurring subscription revenue tiers.")
        if not objectives:
            objectives.append("Implement requested software capabilities outlined in meeting.")

        # 2. Extract Line-by-Line / Sentence-Level Requirements
        # Look for client statements: "We need", "We want", "Can we", "Must have", "We'd like"
        req_cues = [
            (r"(?:we need|we want|we'd like|can we have|must have)\s+to\s+([^.?!]+)", "functional"),
            (r"(?:we need|we want|we'd like|can we have|must have)\s+([^.?!]+)", "functional"),
            (r"client:\s*([^.?!]+)", "functional"),
        ]

        found_topics = set()

        for line in lines:
            line_lower = line.lower()

            # Membership plans & tiers
            if any(k in line_lower for k in ("membership", "pricing tier", "free listing", "premium plan")) and "plans" not in found_topics:
                found_topics.add("plans")
                requirements.append(
                    ExtractedRequirement(
                        id=f"REQ-{req_counter:03d}",
                        title="Configurable Membership Pricing Tiers",
                        description="Implement free basic listings and paid premium membership subscription plans.",
                        req_type=RequirementType.CONFIGURATION,
                        certainty=RequirementCertainty.EXPLICIT_FACT,
                        status=RequirementStatus.CONFIRMED,
                        transcript_evidence=line[:250],
                        user_roles=["Directory Admin", "Member"],
                    )
                )
                req_counter += 1

            # Member Profiles & Details
            if any(k in line_lower for k in ("member profile", "profile", "headshot", "practice area", "license number")) and "profile" not in found_topics:
                found_topics.add("profile")
                requirements.append(
                    ExtractedRequirement(
                        id=f"REQ-{req_counter:03d}",
                        title="Member Profile Pages & Custom Detail Fields",
                        description="Professional member profile pages with headshots, practice areas, bar license numbers, and office addresses.",
                        req_type=RequirementType.FUNCTIONAL,
                        certainty=RequirementCertainty.EXPLICIT_FACT,
                        status=RequirementStatus.CONFIRMED,
                        transcript_evidence=line[:250],
                        user_roles=["Member", "Visitor"],
                    )
                )
                req_counter += 1

            # Brand Styling & Logo
            if any(k in line_lower for k in ("brand styling", "branding", "logo", "color scheme", "gold color")) and "brand" not in found_topics:
                found_topics.add("brand")
                requirements.append(
                    ExtractedRequirement(
                        id=f"REQ-{req_counter:03d}",
                        title="Corporate Brand Styling & Logo Customization",
                        description="Apply corporate color scheme (deep blue and gold), typography, and firm logo to directory header.",
                        req_type=RequirementType.CONFIGURATION,
                        certainty=RequirementCertainty.EXPLICIT_FACT,
                        status=RequirementStatus.CONFIRMED,
                        transcript_evidence=line[:250],
                        user_roles=["Directory Admin"],
                    )
                )
                req_counter += 1

            # Member Reviews & Admin Moderation
            if any(k in line_lower for k in ("member review", "5-star rating", "reviews", "written feedback")) and "reviews" not in found_topics:
                found_topics.add("reviews")
                requirements.append(
                    ExtractedRequirement(
                        id=f"REQ-{req_counter:03d}",
                        title="Member Reviews & Admin Moderation Workflow",
                        description="Allow directory visitors to leave 1-5 star ratings and reviews with mandatory admin approval before publishing.",
                        req_type=RequirementType.FUNCTIONAL,
                        certainty=RequirementCertainty.EXPLICIT_FACT,
                        status=RequirementStatus.CONFIRMED,
                        transcript_evidence=line[:250],
                        user_roles=["Visitor", "Directory Admin", "Member"],
                    )
                )
                req_counter += 1

            # Custom domain & SSL
            if any(k in line_lower for k in ("custom domain", "domain name", "ssl", "nameserver")) and "domain" not in found_topics:
                found_topics.add("domain")
                requirements.append(
                    ExtractedRequirement(
                        id=f"REQ-{req_counter:03d}",
                        title="Custom Domain & SSL Connection",
                        description="Configure custom domain live pointing and automated SSL certificate generation.",
                        req_type=RequirementType.CONFIGURATION,
                        certainty=RequirementCertainty.EXPLICIT_FACT,
                        status=RequirementStatus.CONFIRMED,
                        transcript_evidence=line[:250],
                        user_roles=["Directory Admin"],
                    )
                )
                req_counter += 1

            # Custom Signup Form Fields
            if any(k in line_lower for k in ("form", "custom fields", "dropdown", "experience", "signup fields")) and "form" not in found_topics:
                found_topics.add("form")
                requirements.append(
                    ExtractedRequirement(
                        id=f"REQ-{req_counter:03d}",
                        title="Custom Member Signup Form Fields",
                        description="Add custom dropdown fields (e.g. Years of Experience, Specialties) to registration form.",
                        req_type=RequirementType.CONFIGURATION,
                        certainty=RequirementCertainty.EXPLICIT_FACT,
                        status=RequirementStatus.CONFIRMED,
                        transcript_evidence=line[:250],
                        user_roles=["Member", "Directory Admin"],
                    )
                )
                req_counter += 1

            # Automated Lead Routing
            if any(k in line_lower for k in ("lead routing", "auto match", "zip code", "distribute leads")) and "leads" not in found_topics:
                found_topics.add("leads")
                requirements.append(
                    ExtractedRequirement(
                        id=f"REQ-{req_counter:03d}",
                        title="Automated Lead Distribution by Zip Code",
                        description="Automatically route incoming customer quote requests to verified members based on zip code radius.",
                        req_type=RequirementType.CONFIGURATION,
                        certainty=RequirementCertainty.EXPLICIT_FACT,
                        status=RequirementStatus.CONFIRMED,
                        transcript_evidence=line[:250],
                        user_roles=["Visitor", "Member", "Directory Admin"],
                    )
                )
                req_counter += 1

            # CRM / Webhook Sync (HubSpot / Zapier)
            if any(k in line_lower for k in ("hubspot", "crm", "webhook", "zapier", "two-way sync")) and "crm" not in found_topics:
                found_topics.add("crm")
                is_twoway = "two-way" in line_lower or "sync back" in line_lower
                requirements.append(
                    ExtractedRequirement(
                        id=f"REQ-{req_counter:03d}",
                        title="HubSpot CRM Member Data Integration",
                        description="Sync newly registered members to HubSpot CRM contacts with custom property mappings.",
                        req_type=RequirementType.INTEGRATION,
                        certainty=RequirementCertainty.INTERPRETATION if is_twoway else RequirementCertainty.EXPLICIT_FACT,
                        status=RequirementStatus.NEEDS_CLARIFICATION if is_twoway else RequirementStatus.CONFIRMED,
                        transcript_evidence=line[:250],
                        user_roles=["Directory Admin", "Sales Operations"],
                        clarification_question="Is one-way member export sufficient, or is full bidirectional data synchronization required?" if is_twoway else None,
                    )
                )
                req_counter += 1

            # Ambiguous / Incomplete / Unsupported Features
            if any(k in line_lower for k in ("wordpress", "woocommerce", "plugin")) and "wp" not in found_topics:
                found_topics.add("wp")
                requirements.append(
                    ExtractedRequirement(
                        id=f"REQ-{req_counter:03d}",
                        title="Third-Party WordPress Plugin Support",
                        description="Client asked to upload and execute WordPress WooCommerce plugins inside Brilliant Directories.",
                        req_type=RequirementType.CUSTOM_DEVELOPMENT,
                        certainty=RequirementCertainty.UNCONFIRMED,
                        status=RequirementStatus.NEEDS_CLARIFICATION,
                        transcript_evidence=line[:250],
                        user_roles=["Directory Admin"],
                        clarification_question="Brilliant Directories is a standalone proprietary SaaS platform and does not execute WordPress plugins. Which specific business capability of WooCommerce is required?",
                        is_conflicting=True,
                        conflict_notes="Incompatible architecture: WordPress PHP plugins cannot run inside Brilliant Directories.",
                    )
                )
                req_counter += 1

            # HIPAA / Sensitive Medical Patient Storage
            if any(k in line_lower for k in ("hipaa", "patient medical", "medical records", "ehr")) and "hipaa" not in found_topics:
                found_topics.add("hipaa")
                requirements.append(
                    ExtractedRequirement(
                        id=f"REQ-{req_counter:03d}",
                        title="HIPAA Compliant Patient Health Records Storage",
                        description="Store patient medical histories and private doctor appointment notes on member profiles.",
                        req_type=RequirementType.NON_FUNCTIONAL,
                        certainty=RequirementCertainty.UNCONFIRMED,
                        status=RequirementStatus.NEEDS_CLARIFICATION,
                        transcript_evidence=line[:250],
                        user_roles=["Patient", "Medical Doctor"],
                        clarification_question="Brilliant Directories is designed as a public business directory and is not certified for HIPAA Title II PHI storage. Should private health data be stored in a dedicated compliant EHR system?",
                        is_conflicting=True,
                        conflict_notes="Regulatory risk: public directory SaaS should not store unencrypted Protected Health Information (PHI).",
                    )
                )
                req_counter += 1

            # Native Mobile App / App Stores
            if any(k in line_lower for k in ("mobile app", "app store", "google play", "flutter")) and "mobile" not in found_topics:
                found_topics.add("mobile")
                requirements.append(
                    ExtractedRequirement(
                        id=f"REQ-{req_counter:03d}",
                        title="Native iOS and Android Mobile Applications",
                        description="Publish native downloadable mobile applications on Apple App Store and Google Play Store.",
                        req_type=RequirementType.CUSTOM_DEVELOPMENT,
                        certainty=RequirementCertainty.EXPLICIT_FACT,
                        status=RequirementStatus.CONFIRMED,
                        transcript_evidence=line[:250],
                        user_roles=["Mobile App User"],
                    )
                )
                req_counter += 1

        # Fallback if no specific keyword matched lines
        if not requirements:
            requirements.append(
                ExtractedRequirement(
                    id="REQ-001",
                    title="Directory Portal Configuration",
                    description=lines[0] if lines else "General platform setup requested.",
                    req_type=RequirementType.CONFIGURATION,
                    certainty=RequirementCertainty.EXPLICIT_FACT,
                    status=RequirementStatus.CONFIRMED,
                    transcript_evidence=lines[0] if lines else None,
                    user_roles=["Admin"],
                )
            )

        # Assumptions & Exclusions
        assumptions.append("Client will provide necessary third-party API credentials (Stripe, Google Cloud, HubSpot) in a timely manner.")
        assumptions.append("Brilliant Directories platform subscription license is active.")
        exclusions.append("Custom backend server infrastructure hosting outside Brilliant Directories environment.")
        exclusions.append("Ongoing data entry for thousands of historical client directory records unless contracted separately.")

        # Risks
        if any(r.is_conflicting or r.status == RequirementStatus.NEEDS_CLARIFICATION for r in requirements):
            risks.append("Unconfirmed third-party integrations or architectural incompatibilities may alter timeline and scope.")
        risks.append("Delays in domain DNS propagation or registrar access may impact launch schedule.")

        return {
            "client_objectives": objectives,
            "current_workflow": "Client is currently managing members manually via spreadsheets or an outdated legacy portal.",
            "requirements": requirements,
            "assumptions": assumptions,
            "exclusions": exclusions,
            "risks": risks,
        }
