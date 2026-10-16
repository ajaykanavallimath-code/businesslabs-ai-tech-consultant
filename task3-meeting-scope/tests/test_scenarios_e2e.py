"""
End-to-End tests exercising the three synthetic scenarios:
- Scenario A: Initial client meeting with clear requirements and standard capabilities.
- Scenario B: Ambiguous, conflicting, and unsupported requirements requiring clarification and expert review.
- Scenario C: Follow-up meeting detecting changes, scope deltas, out-of-scope requests, and version evolution.
"""

import pytest
from src.models import ProposalStatus, RequirementStatus, CapabilityStatus


@pytest.mark.asyncio
async def test_scenario_a_e2e(test_workflow, test_review_service, scenario_a_data):
    """
    Scenario A End-to-End:
    Initial client meeting -> Requirement extraction with citations ->
    Capability check -> Scope v1.0 -> Proposal draft -> Human approval -> Client delivery.
    """
    res = await test_workflow.process_initial_meeting(
        project_id=scenario_a_data["project_id"],
        title=scenario_a_data["title"],
        transcript_text=scenario_a_data["transcript"],
        client_name=scenario_a_data["client_name"],
    )

    scope = res["scope"]
    proposal = res["proposal"]

    # 1. Scope and proposal generated
    assert res["project_id"] == "PRJ-LEGAL-01"
    assert res["version"] == "v1.0"
    assert len(scope.requirements) >= 4
    assert scope.total_estimated_hours > 0

    # 2. Every requirement has transcript evidence
    for req in scope.requirements:
        assert req.transcript_evidence is not None
        assert len(req.transcript_evidence) > 0

    # 3. Tasks have bottom-up hour estimates matching total
    sum_hours = round(sum(t.estimated_hours for t in scope.tasks), 2)
    assert scope.total_estimated_hours == sum_hours

    # 4. Proposal starts strictly as DRAFT
    assert proposal.status == ProposalStatus.DRAFT
    assert proposal.delivered_to_client is False

    # 5. Delivery attempt before approval MUST be blocked
    with pytest.raises(PermissionError):
        test_review_service.deliver_proposal(
            proposal_id=proposal.proposal_id,
            recipient_email="sarah@acmelegal.com",
            delivered_by="Consultant Dave",
        )

    # 6. Explicit human approval
    approved = test_review_service.approve_proposal(
        proposal_id=proposal.proposal_id,
        reviewer_id="Senior Architect Bob",
        comments="Scope validated against BD standard settings.",
    )
    assert approved.status == ProposalStatus.APPROVED

    # 7. Delivery succeeds now that proposal is approved
    delivery_res = test_review_service.deliver_proposal(
        proposal_id=proposal.proposal_id,
        recipient_email="sarah@acmelegal.com",
        delivered_by="Consultant Dave",
    )
    assert delivery_res["success"] is True


@pytest.mark.asyncio
async def test_scenario_b_e2e(test_workflow, scenario_b_data):
    """
    Scenario B End-to-End:
    Ambiguous, conflicting, and unsupported requirements (HIPAA records, WordPress PHP plugins, native app stores).
    Verifies detection of conflicts, formulation of clarification questions,
    flagging expert review, and generating qualified drafts without false certainty.
    """
    res = await test_workflow.process_initial_meeting(
        project_id=scenario_b_data["project_id"],
        title=scenario_b_data["title"],
        transcript_text=scenario_b_data["transcript"],
        client_name=scenario_b_data["client_name"],
    )

    scope = res["scope"]
    proposal = res["proposal"]

    # 1. Should identify conflicting/ambiguous requirements
    conflicts = [r for r in scope.requirements if r.is_conflicting]
    clarifications = [r for r in scope.requirements if r.clarification_question is not None]

    assert len(conflicts) > 0, "Scenario B must identify architectural conflicts"
    assert len(clarifications) > 0, "Scenario B must formulate clarification questions"

    # 2. Scope must flag items requiring human or expert review
    assert len(scope.items_requiring_human_review) > 0

    # 3. Uncertain/unsupported tasks should be marked provisional
    provisional_tasks = [t for t in scope.tasks if t.is_provisional]
    assert len(provisional_tasks) > 0

    # 4. Proposal risks and questions must reflect these uncertainties
    assert len(proposal.risks_and_questions) > 0


@pytest.mark.asyncio
async def test_scenario_c_e2e(test_workflow, test_review_service, scenario_a_data, scenario_c_data):
    """
    Scenario C End-to-End:
    Follow-up meeting to Scenario A.
    Verifies baseline scope v1.0 preservation, change detection (modified, removed, added, out of scope),
    net hour delta calculation, revised Scope v2.0 generation, and renewed approval gate.
    """
    # First: process initial meeting (Scenario A)
    init_res = await test_workflow.process_initial_meeting(
        project_id=scenario_a_data["project_id"],
        title=scenario_a_data["title"],
        transcript_text=scenario_a_data["transcript"],
        client_name=scenario_a_data["client_name"],
    )
    baseline_scope = init_res["scope"]
    baseline_hours = baseline_scope.total_estimated_hours

    # Approve initial proposal
    test_review_service.approve_proposal(
        proposal_id=init_res["proposal"].proposal_id,
        reviewer_id="Architect",
    )

    # Second: process follow-up meeting (Scenario C)
    follow_res = await test_workflow.process_followup_meeting(
        project_id=scenario_c_data["project_id"],
        title=scenario_c_data["title"],
        transcript_text=scenario_c_data["transcript"],
        client_name=scenario_c_data["client_name"],
        new_version="v2.0",
    )

    change_report = follow_res["change_report"]
    revised_scope = follow_res["revised_scope"]
    revised_proposal = follow_res["revised_proposal"]

    # 1. Baseline scope remains v1.0 and preserved
    stored_v1 = test_workflow.storage.get_scope(scenario_a_data["project_id"], "v1.0")
    assert stored_v1 is not None
    assert stored_v1.version == "v1.0"
    assert stored_v1.total_estimated_hours == baseline_hours

    # 2. Revised scope has version v2.0
    assert revised_scope.version == "v2.0"
    assert revised_proposal.scope_version == "v2.0"

    # 3. Change report detects changes and calculates delta
    assert len(change_report.changes) >= 3
    assert len(change_report.out_of_scope_requests) >= 1
    assert change_report.net_hour_delta == round(revised_scope.total_estimated_hours - baseline_hours, 2)

    # 4. Prior proposal is marked SUPERSEDED
    old_prop = test_workflow.storage.get_proposal(init_res["proposal"].proposal_id)
    assert old_prop.status == ProposalStatus.SUPERSEDED

    # 5. Revised proposal v2.0 starts in DRAFT status and CANNOT be delivered without new approval
    assert revised_proposal.status == ProposalStatus.DRAFT
    with pytest.raises(PermissionError):
        test_review_service.deliver_proposal(
            proposal_id=revised_proposal.proposal_id,
            recipient_email="sarah@acmelegal.com",
            delivered_by="Consultant Dave",
        )

    # 6. Approving revised proposal allows delivery
    test_review_service.approve_proposal(
        proposal_id=revised_proposal.proposal_id,
        reviewer_id="Partner Jane",
        comments="Approved revised v2.0 scope with Zapier integration.",
    )
    delivery_v2 = test_review_service.deliver_proposal(
        proposal_id=revised_proposal.proposal_id,
        recipient_email="sarah@acmelegal.com",
        delivered_by="Consultant Dave",
    )
    assert delivery_v2["success"] is True
