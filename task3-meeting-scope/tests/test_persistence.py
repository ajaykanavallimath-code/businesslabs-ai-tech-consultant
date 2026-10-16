"""
Tests for Task3Storage persistence and reload integrity across application restarts.
"""

import pytest
from src.storage import Task3Storage
from src.models import (
    ScopeOfWork,
    ProposalDraft,
    MeetingTranscriptRecord,
    ReviewDecisionRecord,
    ReviewAction,
)


def test_storage_reload_integrity(temp_dir):
    """Verify all records survive application restart and reload from file."""
    storage1 = Task3Storage(data_dir=str(temp_dir))

    # Save transcript
    t = MeetingTranscriptRecord(
        transcript_id="TRN-001",
        project_id="PRJ-PERSIST-01",
        title="Initial Call",
        raw_text="Transcript raw content.",
    )
    storage1.save_transcript(t)

    # Save scope
    s = ScopeOfWork(
        scope_id="SCP-001",
        project_id="PRJ-PERSIST-01",
        version="v1.0",
        project_title="Persisted Project",
        total_estimated_hours=28.5,
    )
    storage1.save_scope(s)

    # Save proposal
    p = ProposalDraft(
        proposal_id="PRP-001",
        project_id="PRJ-PERSIST-01",
        scope_version="v1.0",
        title="Persisted Proposal",
        executive_summary="Summary",
        recommended_solution="Solution",
        total_estimated_hours=28.5,
    )
    storage1.save_proposal(p)

    # Save review decision
    d = ReviewDecisionRecord(
        decision_id="DEC-001",
        project_id="PRJ-PERSIST-01",
        proposal_id="PRP-001",
        scope_version="v1.0",
        action=ReviewAction.APPROVE,
        reviewer_id="Admin",
    )
    storage1.save_review_decision(d)

    # Simulate restart by instantiating new storage pointing to same directory
    storage2 = Task3Storage(data_dir=str(temp_dir))

    reloaded_t = storage2.get_transcript("TRN-001")
    assert reloaded_t is not None
    assert reloaded_t.project_id == "PRJ-PERSIST-01"

    reloaded_s = storage2.get_scope("PRJ-PERSIST-01", "v1.0")
    assert reloaded_s is not None
    assert reloaded_s.total_estimated_hours == 28.5

    reloaded_p = storage2.get_proposal("PRP-001")
    assert reloaded_p is not None
    assert reloaded_p.proposal_id == "PRP-001"

    decisions = storage2.list_review_decisions("PRJ-PERSIST-01")
    assert len(decisions) == 1
    assert decisions[0].reviewer_id == "Admin"
