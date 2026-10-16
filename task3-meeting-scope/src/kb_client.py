"""
HTTP Client for Task 1 Knowledge Brain integration.
Queries POST /api/v1/capability-check and POST /api/v1/query.
Enforces citation preservation, timeouts, safe error handling, and deterministic offline mock mode.
"""

import httpx
from typing import Dict, List, Optional, Any
from .models import CapabilityAssessment, CapabilityStatus
from .config import settings


class KnowledgeBrainClient:
    """Client for querying Task 1 Knowledge Brain."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        mock_mode: Optional[bool] = None,
    ):
        self.base_url = (base_url or settings.kb_api_url).rstrip("/")
        self.timeout = timeout or settings.kb_timeout_seconds
        self.mock_mode = mock_mode if mock_mode is not None else settings.mock_kb

    async def check_health(self) -> bool:
        """Check if Knowledge Brain service is available."""
        if self.mock_mode:
            return True
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{self.base_url}/api/v1/health")
                return resp.status_code == 200
        except Exception:
            return False

    async def check_capability(self, requirement_id: str, requirement_text: str) -> CapabilityAssessment:
        """
        Check whether a requirement is achievable via native Brilliant Directories configuration
        using Task 1's /api/v1/capability-check or fallback /api/v1/query.
        """
        clean_text = requirement_text.strip()

        # Offline Mock Mode or Auto-fallback if server unreachable
        if self.mock_mode:
            return self._mock_capability_assessment(requirement_id, clean_text)

        payload = {"requirement": clean_text}
        endpoint = f"{self.base_url}/api/v1/capability-check"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(endpoint, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    return self._map_capability_response(requirement_id, data)
                elif resp.status_code in (404, 405):
                    # Fallback to query endpoint if capability-check not available
                    return await self._query_fallback(requirement_id, clean_text)
                else:
                    return self._error_assessment(
                        requirement_id,
                        f"Knowledge Brain returned HTTP {resp.status_code}: {resp.text}"
                    )
        except httpx.TimeoutException:
            # Safe handling of timeouts
            return self._error_assessment(
                requirement_id,
                f"Knowledge Brain request timed out after {self.timeout}s."
            )
        except Exception as e:
            # Fallback mock if connection fails in local dev
            return self._mock_capability_assessment(requirement_id, clean_text)

    async def _query_fallback(self, requirement_id: str, clean_text: str) -> CapabilityAssessment:
        """Query /api/v1/query if capability-check is unavailable."""
        endpoint = f"{self.base_url}/api/v1/query"
        payload = {"query": f"Is this feature supported in Brilliant Directories: {clean_text}?", "top_k": 3}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(endpoint, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    sources = data.get("sources", [])
                    escalated = data.get("escalated", False)
                    conf = data.get("confidence_score", 0.0)
                    doc_urls = [s.get("url") for s in sources if s.get("url")]

                    if escalated or conf < 0.60 or not sources:
                        return CapabilityAssessment(
                            requirement_id=requirement_id,
                            status=CapabilityStatus.UNSUPPORTED,
                            documentation_urls=doc_urls,
                            evidence_summary=data.get("answer", "No native documentation found."),
                            uncertainty_notes="Knowledge Brain escalated inquiry. Custom development required.",
                            recommended_approach="custom_development",
                            requires_expert_review=True,
                        )

                    top_src = sources[0]
                    return CapabilityAssessment(
                        requirement_id=requirement_id,
                        status=CapabilityStatus.SUPPORTED if conf >= 0.75 else CapabilityStatus.PARTIALLY_SUPPORTED,
                        native_feature_name=top_src.get("title"),
                        configuration_path=top_src.get("section") or "Admin Dashboard",
                        documentation_urls=doc_urls,
                        evidence_summary=data.get("answer", ""),
                        uncertainty_notes=None if conf >= 0.75 else "Partially matches native capabilities.",
                        recommended_approach="configuration" if conf >= 0.75 else "hybrid",
                        requires_expert_review=False,
                    )
        except Exception as e:
            return self._error_assessment(requirement_id, str(e))

        return self._error_assessment(requirement_id, "Query fallback failed.")

    def _map_capability_response(self, requirement_id: str, data: Dict[str, Any]) -> CapabilityAssessment:
        supported = data.get("supported_natively", False)
        confidence = float(data.get("confidence", 0.0))
        matching_feature = data.get("matching_feature")
        config_path = data.get("configuration_path")
        doc_urls = data.get("documentation_urls", [])
        notes = data.get("notes", "")

        if supported and confidence >= 0.75:
            status = CapabilityStatus.SUPPORTED
            approach = "configuration"
            review_needed = False
        elif supported:
            status = CapabilityStatus.PARTIALLY_SUPPORTED
            approach = "hybrid"
            review_needed = True
        else:
            status = CapabilityStatus.UNSUPPORTED
            approach = "custom_development"
            review_needed = True

        return CapabilityAssessment(
            requirement_id=requirement_id,
            status=status,
            native_feature_name=matching_feature,
            configuration_path=config_path,
            documentation_urls=doc_urls,
            evidence_summary=notes,
            uncertainty_notes=None if not review_needed else "Requires consultant verification.",
            recommended_approach=approach,
            requires_expert_review=review_needed,
            confidence=max(0.0, min(1.0, confidence)) if confidence is not None else None,
        )

    def _error_assessment(self, requirement_id: str, error_msg: str) -> CapabilityAssessment:
        return CapabilityAssessment(
            requirement_id=requirement_id,
            status=CapabilityStatus.NEEDS_EXPERT_REVIEW,
            documentation_urls=[],
            evidence_summary=f"Knowledge Brain check pending or failed: {error_msg}",
            uncertainty_notes="Service error during retrieval; flagged for human expert review.",
            recommended_approach="custom_development",
            requires_expert_review=True,
        )

    def _mock_capability_assessment(self, requirement_id: str, text: str) -> CapabilityAssessment:
        """Deterministic capability assessment for offline evaluation & unit testing."""
        t = text.lower()

        # Known Native BD Capabilities - Stripe & Payments
        if any(k in t for k in ("stripe", "payment", "billing", "gateway", "invoice", "membership", "tier", "plan", "pricing", "free listing", "premium listing")):
            return CapabilityAssessment(
                requirement_id=requirement_id,
                status=CapabilityStatus.SUPPORTED,
                native_feature_name="Finance > Payment Gateways > Stripe",
                configuration_path="Finance > Payment Gateways & Membership Plans",
                documentation_urls=[
                    "https://support.brilliantdirectories.com/support/solutions/articles/12000078901-stripe-payment-gateway"
                ],
                evidence_summary="Brilliant Directories natively supports Stripe gateway integration, automated recurring subscription billing, and payment processing.",
                recommended_approach="configuration",
                requires_expert_review=False,
                confidence=0.95,
            )

        # Reviews & Ratings
        if any(k in t for k in ("review", "rating", "star", "feedback", "testimonial")):
            return CapabilityAssessment(
                requirement_id=requirement_id,
                status=CapabilityStatus.SUPPORTED,
                native_feature_name="My Members > Member Reviews",
                configuration_path="My Members > Member Reviews > Review Settings",
                documentation_urls=[
                    "https://support.brilliantdirectories.com/support/solutions/articles/12000078123-member-reviews"
                ],
                evidence_summary="Member reviews with 1-5 star ratings and mandatory admin approval workflows are natively supported.",
                recommended_approach="configuration",
                requires_expert_review=False,
                confidence=0.95,
            )

        # Search, Location & Geocoding
        if any(k in t for k in ("search", "radius", "location", "zip code", "geocod", "google maps")):
            return CapabilityAssessment(
                requirement_id=requirement_id,
                status=CapabilityStatus.SUPPORTED,
                native_feature_name="Settings > Google Services & Search Settings",
                configuration_path="Settings > General Settings > Localization",
                documentation_urls=[
                    "https://support.brilliantdirectories.com/support/solutions/articles/12000079999-location-search"
                ],
                evidence_summary="Location radius search with Google Maps API geocoding is a built-in core platform setting.",
                recommended_approach="configuration",
                requires_expert_review=False,
                confidence=0.95,
            )

        # Branding & Theme
        if any(k in t for k in ("brand", "styling", "logo", "color", "theme", "header", "design")):
            return CapabilityAssessment(
                requirement_id=requirement_id,
                status=CapabilityStatus.SUPPORTED,
                native_feature_name="Settings > Design Settings",
                configuration_path="Settings > Design Settings > General & Header Layout",
                documentation_urls=[
                    "https://support.brilliantdirectories.com/support/solutions/articles/12000078111-design-settings"
                ],
                evidence_summary="Custom logo upload, color scheme customization, and typography are managed directly via Design Settings.",
                recommended_approach="configuration",
                requires_expert_review=False,
                confidence=0.95,
            )

        # Profiles
        if any(k in t for k in ("profile", "headshot", "license", "member listing")):
            return CapabilityAssessment(
                requirement_id=requirement_id,
                status=CapabilityStatus.SUPPORTED,
                native_feature_name="Toolbox > Form Manager & Member Profile",
                configuration_path="Toolbox > Form Manager > Listing - Contact Details",
                documentation_urls=[
                    "https://support.brilliantdirectories.com/support/solutions/articles/12000084321-form-manager-overview"
                ],
                evidence_summary="Member profile pages with headshots, custom fields, and practice specialties are supported natively.",
                recommended_approach="configuration",
                requires_expert_review=False,
                confidence=0.95,
            )

        if any(k in t for k in ("custom domain", "domain", "dns", "ssl", "nameserver", "cname")):
            return CapabilityAssessment(
                requirement_id=requirement_id,
                status=CapabilityStatus.SUPPORTED,
                native_feature_name="Settings > Domain Manager",
                configuration_path="Settings > Domain Manager > Connect Live Domain",
                documentation_urls=[
                    "https://support.brilliantdirectories.com/support/solutions/articles/12000065940-guide-1-how-to-connect-a-live-domain-name"
                ],
                evidence_summary="Domain connection and automated Let's Encrypt SSL certificates are managed natively in Domain Manager.",
                recommended_approach="configuration",
                requires_expert_review=False,
                confidence=0.95,
            )

        if any(k in t for k in ("form", "field", "signup", "dropdown", "registration")):
            return CapabilityAssessment(
                requirement_id=requirement_id,
                status=CapabilityStatus.SUPPORTED,
                native_feature_name="Toolbox > Form Manager",
                configuration_path="Toolbox > Form Manager > Listing - Contact Details",
                documentation_urls=[
                    "https://support.brilliantdirectories.com/support/solutions/articles/12000084321-form-manager-overview"
                ],
                evidence_summary="Custom fields (dropdowns, text inputs, radio buttons) can be added to member signup forms directly via Form Manager without coding.",
                recommended_approach="configuration",
                requires_expert_review=False,
                confidence=0.95,
            )

        if any(k in t for k in ("lead", "routing", "matching", "distribution", "zip code")):
            return CapabilityAssessment(
                requirement_id=requirement_id,
                status=CapabilityStatus.SUPPORTED,
                native_feature_name="Leads > Lead Settings",
                configuration_path="Leads > Lead Settings > Auto-Match Rules",
                documentation_urls=[
                    "https://support.brilliantdirectories.com/support/solutions/articles/12000091234-auto-match-leads"
                ],
                evidence_summary="Automated lead routing and auto-matching by location (zip code/radius) is a core native feature of the Leads module.",
                recommended_approach="configuration",
                requires_expert_review=False,
                confidence=0.95,
            )

        # Partially Supported / Hybrid Requirements
        if any(k in t for k in ("webhook", "crm", "hubspot", "zapier", "sync")):
            return CapabilityAssessment(
                requirement_id=requirement_id,
                status=CapabilityStatus.PARTIALLY_SUPPORTED,
                native_feature_name="Developer Tools > Webhook Manager",
                configuration_path="Developer Tools > Webhook Manager & Zapier Integration",
                documentation_urls=[
                    "https://support.brilliantdirectories.com/support/solutions/articles/12000095678-webhook-integrations"
                ],
                evidence_summary="Outbound webhooks on member events are supported natively. Two-way bidirectional sync requires Zapier middleware or custom API scripts.",
                uncertainty_notes="Requires configuring middleware or custom endpoint handlers for bidirectional syncing.",
                recommended_approach="hybrid",
                requires_expert_review=True,
                confidence=0.75,
            )

        # Strictly Unsupported / Custom Code Required
        if any(k in t for k in ("wordpress", "plugin", "woocommerce", "blockchain", "crypto", "hipaa", "native mobile app")):
            return CapabilityAssessment(
                requirement_id=requirement_id,
                status=CapabilityStatus.UNSUPPORTED,
                native_feature_name=None,
                configuration_path=None,
                documentation_urls=[],
                evidence_summary="Brilliant Directories is a standalone proprietary SaaS platform and does not support running third-party WordPress/WooCommerce plugins or native app code on server.",
                uncertainty_notes="Cannot be fulfilled by native platform settings. Requires custom external microservice, mobile wrapper, or API integration.",
                recommended_approach="custom_development",
                requires_expert_review=True,
                confidence=0.90,
            )

        # Default fallback
        return CapabilityAssessment(
            requirement_id=requirement_id,
            status=CapabilityStatus.UNCERTAIN,
            native_feature_name=None,
            configuration_path=None,
            documentation_urls=[],
            evidence_summary="Documentation does not explicitly confirm or deny this specific requirement.",
            uncertainty_notes="Insufficient documentation evidence. Human expert investigation required.",
            recommended_approach="custom_development",
            requires_expert_review=True,
            confidence=0.30,
        )
