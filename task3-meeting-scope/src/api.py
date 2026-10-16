"""
FastAPI REST API for Task 3: Meeting to Scope.
Provides endpoints for transcript submission, capability review, scope retrieval,
change detection, human review & approval, and secure proposal delivery.
"""

from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .models import (
    ScopeOfWork,
    ProposalDraft,
    ProposalStatus,
    ChangeDetectionReport,
    ExtractedRequirement,
    CapabilityAssessment,
    ReviewDecisionRecord,
)
from .workflow import MeetingToScopeWorkflow
from .review_service import ReviewService
from .storage import Task3Storage
from .config import settings

app = FastAPI(
    title="BusinessLabs Task 3: Meeting to Scope API",
    description="Transforms client meeting transcripts into structured scopes, task estimates, and proposal drafts with human review gates.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared instances
storage = Task3Storage()
workflow = MeetingToScopeWorkflow(storage=storage)
review_service = ReviewService(storage=storage)


# --- Request & Response Schemas ---

class InitialMeetingRequest(BaseModel):
    project_id: str = Field(..., description="Unique project identifier, e.g. PRJ-001")
    title: str = Field(default="Client Discovery Meeting", description="Meeting title")
    transcript_text: str = Field(..., description="Raw text of the meeting transcript")
    client_name: Optional[str] = Field(default="Client", description="Client or company name")
    meeting_date: Optional[str] = None


class FollowupMeetingRequest(BaseModel):
    project_id: str = Field(..., description="Target existing project identifier")
    title: str = Field(default="Follow-up Scope Review", description="Meeting title")
    transcript_text: str = Field(..., description="Raw text of follow-up meeting transcript")
    client_name: Optional[str] = Field(default="Client")
    meeting_date: Optional[str] = None


class ReviewRequest(BaseModel):
    proposal_id: str = Field(..., description="ID of proposal to review")
    action: str = Field(..., description="approve | reject | edit | request_clarification")
    reviewer_id: str = Field(..., description="Name or ID of reviewer")
    comments: Optional[str] = Field(default=None, description="Approval comments or rejection reason")
    executive_summary: Optional[str] = None
    recommended_solution: Optional[str] = None
    commercial_terms: Optional[str] = None


class DeliveryRequest(BaseModel):
    proposal_id: str = Field(..., description="ID of proposal to deliver")
    recipient_email: str = Field(..., description="Client email address")
    delivered_by: str = Field(..., description="Name or ID of authorized sender")


# --- Endpoints ---

@app.get("/api/v1/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "Task 3 Meeting to Scope",
        "mock_llm": settings.mock_llm,
        "mock_kb": settings.mock_kb,
        "enable_client_delivery": settings.enable_client_delivery,
    }


@app.get("/api/v1/scenarios")
async def list_scenarios():
    """List available demo meeting scenarios."""
    import json
    from pathlib import Path
    fixtures_dir = Path(__file__).resolve().parent.parent / "fixtures"
    scenarios = []
    for filename in ["scenario_a_initial.json", "scenario_b_ambiguous.json", "scenario_c_followup.json"]:
        file_path = fixtures_dir / filename
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                scenarios.append(json.load(f))
    return {"success": True, "count": len(scenarios), "scenarios": scenarios}


@app.post("/api/v1/meetings/initial", status_code=status.HTTP_201_CREATED)
async def submit_initial_meeting(req: InitialMeetingRequest):
    """
    Submit and process an initial client meeting transcript.
    Extracts requirements, checks capabilities with Task 1, builds Scope v1.0, and drafts proposal.
    """
    if not req.transcript_text.strip():
        raise HTTPException(status_code=400, detail="Transcript text cannot be empty.")
    try:
        result = await workflow.process_initial_meeting(
            project_id=req.project_id,
            title=req.title,
            transcript_text=req.transcript_text,
            client_name=req.client_name or "Client",
            meeting_date=req.meeting_date,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal processing error: {str(e)}")


@app.post("/api/v1/meetings/followup")
async def submit_followup_meeting(req: FollowupMeetingRequest):
    """
    Submit and process a follow-up meeting transcript linked to an existing project.
    Compares against baseline scope, detects changes, updates hour estimates, and issues Scope v2.0.
    """
    if not req.transcript_text.strip():
        raise HTTPException(status_code=400, detail="Transcript text cannot be empty.")
    try:
        result = await workflow.process_followup_meeting(
            project_id=req.project_id,
            title=req.title,
            transcript_text=req.transcript_text,
            client_name=req.client_name or "Client",
            meeting_date=req.meeting_date,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal processing error: {str(e)}")


@app.get("/api/v1/projects/{project_id}/scope", response_model=ScopeOfWork)
async def get_project_scope(project_id: str, version: Optional[str] = Query(None)):
    """Retrieve the Scope of Work for a project (optionally specific version)."""
    scope = storage.get_scope(project_id, version=version)
    if not scope:
        raise HTTPException(status_code=404, detail=f"Scope not found for project '{project_id}'")
    return scope


@app.get("/api/v1/projects/{project_id}/requirements", response_model=List[ExtractedRequirement])
async def get_project_requirements(project_id: str, version: Optional[str] = Query(None)):
    """Retrieve extracted requirements for a project."""
    scope = storage.get_scope(project_id, version=version)
    if not scope:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")
    return scope.requirements


@app.get("/api/v1/projects/{project_id}/capabilities", response_model=List[CapabilityAssessment])
async def get_project_capabilities(project_id: str, version: Optional[str] = Query(None)):
    """Retrieve Knowledge Brain capability assessment findings."""
    scope = storage.get_scope(project_id, version=version)
    if not scope:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")
    return scope.capability_assessments


@app.get("/api/v1/projects/{project_id}/tasks")
async def get_project_tasks(project_id: str, version: Optional[str] = Query(None)):
    """Retrieve the task breakdown and hour estimates."""
    scope = storage.get_scope(project_id, version=version)
    if not scope:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")
    return {
        "project_id": project_id,
        "scope_version": scope.version,
        "total_estimated_hours": scope.total_estimated_hours,
        "task_count": len(scope.tasks),
        "tasks": scope.tasks,
    }


@app.get("/api/v1/projects/{project_id}/proposal", response_model=ProposalDraft)
async def get_project_proposal(project_id: str, proposal_id: Optional[str] = Query(None)):
    """Retrieve the proposal draft for a project."""
    if proposal_id:
        proposal = storage.get_proposal(proposal_id)
    else:
        proposal = storage.get_latest_proposal(project_id)

    if not proposal:
        raise HTTPException(status_code=404, detail=f"Proposal not found for project '{project_id}'")
    return proposal


@app.get("/api/v1/projects/{project_id}/changes", response_model=List[ChangeDetectionReport])
async def get_change_reports(project_id: str):
    """Retrieve change detection reports comparing meeting versions."""
    reports = storage.get_change_reports_for_project(project_id)
    return reports


@app.post("/api/v1/projects/{project_id}/review", response_model=ProposalDraft)
async def submit_human_review(project_id: str, req: ReviewRequest):
    """
    Submit a human review decision (approve, reject, edit).
    Backend enforces state machine rules.
    """
    action_lower = req.action.lower()
    try:
        if action_lower == "approve":
            return review_service.approve_proposal(
                proposal_id=req.proposal_id,
                reviewer_id=req.reviewer_id,
                comments=req.comments,
            )
        elif action_lower == "reject":
            if not req.comments:
                raise HTTPException(status_code=400, detail="Rejection reason is mandatory.")
            return review_service.reject_proposal(
                proposal_id=req.proposal_id,
                reviewer_id=req.reviewer_id,
                rejection_reason=req.comments,
            )
        elif action_lower == "edit":
            return review_service.edit_proposal_content(
                proposal_id=req.proposal_id,
                reviewer_id=req.reviewer_id,
                executive_summary=req.executive_summary,
                recommended_solution=req.recommended_solution,
                commercial_terms=req.commercial_terms,
            )
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported review action '{req.action}'.")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/v1/projects/{project_id}/deliver")
async def deliver_proposal_endpoint(project_id: str, req: DeliveryRequest):
    """
    Deliver approved proposal to client.
    ENFORCES HARD GATE: Throws HTTP 403 Forbidden if proposal is NOT approved!
    """
    try:
        result = review_service.deliver_proposal(
            proposal_id=req.proposal_id,
            recipient_email=req.recipient_email,
            delivered_by=req.delivered_by,
        )
        return result
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.get("/api/v1/projects/{project_id}/history")
async def get_project_history(project_id: str):
    """Retrieve full audit history including all scopes, proposals, and decisions."""
    scopes = storage.list_scope_versions(project_id)
    proposals = storage.list_proposals(project_id)
    transcripts = storage.list_transcripts(project_id)
    decisions = storage.list_review_decisions(project_id)
    change_reports = storage.get_change_reports_for_project(project_id)

    return {
        "project_id": project_id,
        "scope_versions": [s.version for s in scopes],
        "scopes": scopes,
        "proposals": proposals,
        "transcripts": transcripts,
        "review_decisions": decisions,
        "change_reports": change_reports,
    }
