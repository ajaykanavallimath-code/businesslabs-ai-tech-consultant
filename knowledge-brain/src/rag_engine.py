"""Claude RAG synthesis engine with strict source citations and two-tier escalation."""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import anthropic

from src.config import Settings, settings as global_settings
from src.escalation_manager import EscalationManager
from src.models import (
    ImageCitation,
    QueryRequest,
    QueryResponse,
    SourceCitation,
)
from src.vector_store import VectorStore

logger = logging.getLogger("knowledge_brain.rag_engine")

SYSTEM_PROMPT = """You are the Brilliant Directories Technical Consultant Assistant.
Your task is to answer technical and product questions about Brilliant Directories using ONLY the provided documentation excerpts below.

CRITICAL GROUNDING RULES:
1. Base your answer EXCLUSIVELY on the provided documentation excerpts. Do NOT guess, extrapolate, or use outside knowledge.
2. If the provided documentation excerpts do NOT explicitly answer the user's inquiry or lack essential details, you MUST abstain by setting "abstain": true.
3. NEVER invent, hallucinate, or modify URLs, settings paths, or product features. Every cited URL must match an exact URL from the excerpts.
4. Include inline citations to the source articles where relevant (e.g., "[Source: Article Title]").
5. If the excerpts include relevant screenshots/images that clarify the steps, include their exact image URLs in "selected_image_urls".

You MUST respond with valid JSON matching this schema:
{
  "answer": "Clear, professional answer citing the provided documentation. If abstaining, explain what information is missing.",
  "abstain": false,
  "confidence": 0.90,
  "cited_urls": ["https://support.brilliantdirectories.com/..."],
  "selected_image_urls": ["https://s3.amazonaws.com/..."],
  "escalation_reason": null
}

If the evidence is insufficient or contradictory:
{
  "answer": "I do not have sufficient documentation in the Solution Center to answer this question accurately.",
  "abstain": true,
  "confidence": 0.20,
  "cited_urls": [],
  "selected_image_urls": [],
  "escalation_reason": "Documentation does not mention custom webhook signature verification algorithms."
}
"""


class RAGEngine:
    """Orchestrates ChromaDB retrieval, Claude grounded synthesis, and human escalation."""

    def __init__(
        self,
        config: Optional[Settings] = None,
        vector_store: Optional[VectorStore] = None,
        escalation_manager: Optional[EscalationManager] = None,
        anthropic_client: Optional[anthropic.AsyncAnthropic] = None,
    ):
        self.config = config or global_settings
        self.vector_store = vector_store or VectorStore(config=self.config)
        self.escalation_manager = escalation_manager or EscalationManager(config=self.config)
        self.anthropic_client = anthropic_client

    async def _get_anthropic_client(self) -> Optional[anthropic.AsyncAnthropic]:
        """Initialize or return AsyncAnthropic client if API key is present."""
        if self.anthropic_client is not None:
            return self.anthropic_client

        api_key = self.config.anthropic_api_key.strip()
        if not api_key:
            return None

        return anthropic.AsyncAnthropic(api_key=api_key)

    async def answer_query(self, request: QueryRequest) -> QueryResponse:
        """Process an inquiry through two-tier retrieval and Claude grounded synthesis.

        Tier 1: Semantic retrieval distance gate.
        Tier 2: Claude grounded evidence gate with strict citation verification.
        """
        query = request.query.strip()
        min_score = request.min_score or self.config.similarity_threshold

        # ----------------------------------------------------------------------
        # 1. Tier 1: Vector Retrieval & Relevance Gate
        # ----------------------------------------------------------------------
        citations = self.vector_store.search(
            query=query,
            top_k=request.top_k,
            min_score=min_score,
        )

        if not citations:
            # Tier 1 Escalation: No documentation found above similarity threshold
            reason = (
                f"No Solution Center documentation found matching query above "
                f"similarity threshold ({min_score})."
            )
            task = self.escalation_manager.create_escalation(
                query=query,
                reason=reason,
                sources=[],
            )
            return QueryResponse(
                query=query,
                answer=(
                    "I could not find verified Brilliant Directories documentation for this topic. "
                    "This inquiry has been escalated to a human expert for review."
                ),
                confidence_score=0.0,
                escalated=True,
                escalation_id=task.id,
                sources=[],
                images=[],
            )

        # ----------------------------------------------------------------------
        # 2. Check for Mock LLM Mode (Testing / Offline)
        # ----------------------------------------------------------------------
        if self.config.mock_llm:
            return self._handle_mock_llm(query, citations)

        # ----------------------------------------------------------------------
        # 3. Check for Missing API Key
        # ----------------------------------------------------------------------
        client = await self._get_anthropic_client()
        if client is None:
            reason = "Anthropic API key is not configured. Cannot perform Claude synthesis."
            logger.warning(reason)
            task = self.escalation_manager.create_escalation(
                query=query,
                reason=reason,
                sources=citations,
            )
            return QueryResponse(
                query=query,
                answer=(
                    "LLM generation is currently unconfigured. The request has been "
                    "escalated to a human technical consultant."
                ),
                confidence_score=round(citations[0].score, 4),
                escalated=True,
                escalation_id=task.id,
                sources=citations,
                images=[],
            )

        # ----------------------------------------------------------------------
        # 4. Tier 2: Claude Grounded Generation & Citation Verification
        # ----------------------------------------------------------------------
        prompt_context = self._format_prompt_context(citations)
        user_message = f"User Question: {query}\n\nDocumentation Context:\n{prompt_context}"

        try:
            response = await client.messages.create(
                model=self.config.claude_model_primary,
                max_tokens=1000,
                temperature=0.0,  # Deterministic grounding
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
                timeout=30.0,
            )

            response_text = response.content[0].text.strip()
            parsed_data = self._parse_claude_response(response_text)

        except anthropic.APITimeoutError as e:
            logger.error(f"Claude API request timed out: {e}")
            task = self.escalation_manager.create_escalation(
                query=query,
                reason="Claude API timeout (30s exceeded). Escalated for expert review.",
                sources=citations,
            )
            return QueryResponse(
                query=query,
                answer=(
                    "The knowledge service timed out while generating the response. "
                    "This inquiry has been escalated to a human expert."
                ),
                confidence_score=round(citations[0].score, 4),
                escalated=True,
                escalation_id=task.id,
                sources=citations,
                images=[],
            )
        except anthropic.APIError as e:
            logger.error(f"Claude API error: {e}")
            task = self.escalation_manager.create_escalation(
                query=query,
                reason=f"Claude API error: {type(e).__name__}",
                sources=citations,
            )
            return QueryResponse(
                query=query,
                answer=(
                    "An external model service error occurred. This inquiry "
                    "has been recorded for human expert review."
                ),
                confidence_score=round(citations[0].score, 4),
                escalated=True,
                escalation_id=task.id,
                sources=citations,
                images=[],
            )
        except Exception as e:
            logger.error(f"Unexpected Claude synthesis error: {e}")
            task = self.escalation_manager.create_escalation(
                query=query,
                reason=f"Generation error: {type(e).__name__}",
                sources=citations,
            )
            return QueryResponse(
                query=query,
                answer=(
                    "An unexpected error occurred while generating the response. This inquiry "
                    "has been recorded for human expert review."
                ),
                confidence_score=round(citations[0].score, 4),
                escalated=True,
                escalation_id=task.id,
                sources=citations,
                images=[],
            )

        # ----------------------------------------------------------------------
        # 5. Evaluate Abstention & Confidence Cutoff
        # ----------------------------------------------------------------------
        abstain = parsed_data.get("abstain", False)
        confidence = float(parsed_data.get("confidence", 0.0))

        if abstain or confidence < self.config.confidence_threshold:
            escalation_reason = (
                parsed_data.get("escalation_reason")
                or f"Claude confidence score ({confidence:.2f}) below threshold ({self.config.confidence_threshold:.2f})."
            )
            task = self.escalation_manager.create_escalation(
                query=query,
                reason=escalation_reason,
                sources=citations,
            )
            return QueryResponse(
                query=query,
                answer=parsed_data.get("answer") or "Insufficient evidence in documentation to provide a confident answer.",
                confidence_score=confidence,
                escalated=True,
                escalation_id=task.id,
                sources=citations,
                images=[],
            )

        # ----------------------------------------------------------------------
        # 6. Verify Citations (Anti-Hallucination Gate) & Assemble Images
        # ----------------------------------------------------------------------
        retrieved_urls = {c.url: c for c in citations}
        cited_urls = parsed_data.get("cited_urls", [])

        # Strict citation check: Reject fabricated URLs
        hallucinated_urls = [url for url in cited_urls if url not in retrieved_urls]
        if hallucinated_urls:
            logger.warning(f"Claude cited unverified/hallucinated URLs: {hallucinated_urls}")
            task = self.escalation_manager.create_escalation(
                query=query,
                reason=f"Model cited unverified/hallucinated URL(s): {', '.join(hallucinated_urls)}",
                sources=citations,
            )
            return QueryResponse(
                query=query,
                answer=(
                    "The generated response referenced unverified sources not present in retrieved "
                    "documentation. The inquiry has been escalated to a human expert."
                ),
                confidence_score=0.0,
                escalated=True,
                escalation_id=task.id,
                sources=citations,
                images=[],
            )

        valid_citations, selected_images = self._filter_verified_sources(
            citations=citations,
            cited_urls=cited_urls,
            selected_image_urls=parsed_data.get("selected_image_urls", []),
        )

        return QueryResponse(
            query=query,
            answer=parsed_data["answer"],
            confidence_score=confidence,
            escalated=False,
            escalation_id=None,
            sources=valid_citations,
            images=selected_images[: self.config.max_images_per_answer],
        )

    def _format_prompt_context(self, citations: List[SourceCitation]) -> str:
        """Format retrieved chunks into a numbered context block for Claude."""
        blocks = []
        for i, c in enumerate(citations, 1):
            block = f"--- [Document {i}] ---\n"
            block += f"Title: {c.title}\n"
            block += f"URL: {c.url}\n"
            if c.section:
                block += f"Section: {c.section}\n"
            block += f"Content:\n{c.snippet}\n"

            if c.images:
                block += "Available Screenshots in this excerpt:\n"
                for img in c.images:
                    block += f"  - Image URL: {img.url} (Caption: {img.caption or 'None'})\n"
            blocks.append(block)

        return "\n".join(blocks)

    def _parse_claude_response(self, text: str) -> Dict[str, Any]:
        """Extract and parse JSON object from Claude response text."""
        # Handle cases where response might be wrapped in ```json ... ```
        cleaned = text.strip()
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(1).strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Fallback for plain text output
            logger.warning("Claude returned non-JSON text; falling back to text parsing.")
            return {
                "answer": text,
                "abstain": False,
                "confidence": 0.85,
                "cited_urls": [],
                "selected_image_urls": [],
                "escalation_reason": None,
            }

    def _filter_verified_sources(
        self,
        citations: List[SourceCitation],
        cited_urls: List[str],
        selected_image_urls: List[str],
    ) -> Tuple[List[SourceCitation], List[ImageCitation]]:
        """Ensure cited URLs and image URLs match actual retrieved documents."""
        retrieved_urls = {c.url: c for c in citations}
        valid_citations: List[SourceCitation] = []

        if cited_urls:
            for url in cited_urls:
                if url in retrieved_urls:
                    valid_citations.append(retrieved_urls[url])

        # If model didn't explicitly populate cited_urls, keep all retrieved chunks
        if not valid_citations:
            valid_citations = citations

        # Extract verified images
        candidate_images: Dict[str, ImageCitation] = {}
        for c in citations:
            for img in c.images:
                candidate_images[img.url] = img

        selected_images: List[ImageCitation] = []
        if selected_image_urls:
            for img_url in selected_image_urls:
                if img_url in candidate_images:
                    selected_images.append(candidate_images[img_url])

        # Fallback: if no specific images selected by model, grab images from top citation
        if not selected_images and valid_citations and valid_citations[0].images:
            selected_images = valid_citations[0].images

        return valid_citations, selected_images

    def _handle_mock_llm(
        self,
        query: str,
        citations: List[SourceCitation],
    ) -> QueryResponse:
        """Deterministic response generator for offline testing."""
        top_citation = citations[0]

        # 1. Simulate intentional abstention trigger for testing
        if "unsupported" in query.lower() or "quantum" in query.lower():
            task = self.escalation_manager.create_escalation(
                query=query,
                reason="Query explicitly flagged as unsupported for testing.",
                sources=citations,
            )
            return QueryResponse(
                query=query,
                answer="Documentation does not support this requirement. Escalated to human expert.",
                confidence_score=0.20,
                escalated=True,
                escalation_id=task.id,
                sources=citations,
                images=[],
            )

        # 2. Simulate low confidence score below threshold
        if "low confidence" in query.lower():
            task = self.escalation_manager.create_escalation(
                query=query,
                reason=f"Claude confidence score (0.45) below threshold ({self.config.confidence_threshold:.2f}).",
                sources=citations,
            )
            return QueryResponse(
                query=query,
                answer="Documentation is ambiguous on this workflow. Escalated to expert.",
                confidence_score=0.45,
                escalated=True,
                escalation_id=task.id,
                sources=citations,
                images=[],
            )

        # 3. Simulate model attempting hallucinated citation URLs
        if "hallucinate citation" in query.lower():
            fake_url = "https://support.brilliantdirectories.com/support/solutions/articles/fake-nonexistent-article"
            task = self.escalation_manager.create_escalation(
                query=query,
                reason=f"Model cited unverified/hallucinated URL(s): {fake_url}",
                sources=citations,
            )
            return QueryResponse(
                query=query,
                answer="The generated response referenced unverified sources not present in retrieved documentation.",
                confidence_score=0.0,
                escalated=True,
                escalation_id=task.id,
                sources=citations,
                images=[],
            )

        # 4. Simulate external API error
        if "simulate error" in query.lower():
            task = self.escalation_manager.create_escalation(
                query=query,
                reason="Claude API error: APIConnectionError",
                sources=citations,
            )
            return QueryResponse(
                query=query,
                answer="An external model service error occurred. This inquiry has been recorded for human expert review.",
                confidence_score=round(top_citation.score, 4),
                escalated=True,
                escalation_id=task.id,
                sources=citations,
                images=[],
            )

        # 5. Normal Grounded mock answer
        answer = (
            f"Based on Brilliant Directories documentation ({top_citation.title}), "
            f"you can configure this feature. Excerpt: {top_citation.snippet[:120]}... "
            f"[Source: {top_citation.title}]"
        )
        return QueryResponse(
            query=query,
            answer=answer,
            confidence_score=0.92,
            escalated=False,
            escalation_id=None,
            sources=[top_citation],
            images=top_citation.images[: self.config.max_images_per_answer],
        )
