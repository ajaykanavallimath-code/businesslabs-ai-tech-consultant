"""
Tests for Agent 1: Meeting Analyst.
Verifies requirement extraction, evidence traceability, ambiguous and conflicting requirement handling,
and empty transcript validation.
"""

import pytest
from src.agents.analyst import MeetingAnalyst
from src.models import RequirementCertainty, RequirementStatus


@pytest.mark.asyncio
async def test_analyst_extracts_requirements_with_evidence(scenario_a_data):
    """Verify MeetingAnalyst extracts requirements with traceable transcript evidence."""
    analyst = MeetingAnalyst()
    result = await analyst.analyze_transcript(
        transcript_text=scenario_a_data["transcript"],
        project_id="PRJ-LEGAL-01",
        title=scenario_a_data["title"],
    )

    reqs = result["requirements"]
    assert len(reqs) >= 4

    # Verify every requirement has non-empty evidence from transcript
    for req in reqs:
        assert req.id.startswith("REQ-")
        assert req.transcript_evidence is not None
        assert len(req.transcript_evidence) > 0
        # Verify evidence text actually exists in raw transcript
        assert req.transcript_evidence.strip() in scenario_a_data["transcript"]

    # Verify objectives, assumptions, and exclusions are extracted
    assert len(result["client_objectives"]) > 0
    assert len(result["assumptions"]) > 0
    assert len(result["exclusions"]) > 0


@pytest.mark.asyncio
async def test_analyst_detects_ambiguity_and_conflicts(scenario_b_data):
    """Verify MeetingAnalyst flags conflicting architectures and generates clarification questions."""
    analyst = MeetingAnalyst()
    result = await analyst.analyze_transcript(
        transcript_text=scenario_b_data["transcript"],
        project_id="PRJ-HEALTH-02",
        title=scenario_b_data["title"],
    )

    reqs = result["requirements"]
    conflicting_reqs = [r for r in reqs if r.is_conflicting]
    clarification_reqs = [r for r in reqs if r.clarification_question is not None]

    assert len(conflicting_reqs) > 0, "Should detect architectural/regulatory conflicts (HIPAA or WordPress plugin)"
    assert len(clarification_reqs) > 0, "Should generate clarification questions for ambiguous/conflicting items"

    # Specific check on HIPAA requirement
    hipaa_req = next((r for r in reqs if "hipaa" in r.title.lower()), None)
    if hipaa_req:
        assert hipaa_req.certainty == RequirementCertainty.UNCONFIRMED
        assert hipaa_req.status == RequirementStatus.NEEDS_CLARIFICATION
        assert "?" in (hipaa_req.clarification_question or "")


@pytest.mark.asyncio
async def test_analyst_empty_transcript_rejected():
    """Verify empty or whitespace-only transcript is rejected with ValueError."""
    analyst = MeetingAnalyst()
    with pytest.raises(ValueError, match="cannot be empty"):
        await analyst.analyze_transcript(
            transcript_text="   \n  \t ",
            project_id="PRJ-EMPTY",
        )
