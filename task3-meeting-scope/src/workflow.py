"""
Orchestration workflow for Task 3: Meeting to Scope.
Coordinates MeetingAnalyst, CapabilityAnalyst, ScopePlanner, ProposalWriter, and DiffEngine.
Ensures persistent storage, full traceability, and strict version control.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import uuid

from .models import (
    MeetingTranscriptRecord,
    ScopeOfWork,
    ProposalDraft,
    ProposalStatus,
    ChangeDetectionReport,
)
from .storage import Task3Storage
from .kb_client import KnowledgeBrainClient
from .agents import (
    MeetingAnalyst,
    CapabilityAnalyst,
    ScopePlanner,
    ProposalWriter,
    DiffEngine,
)
from .config import settings


class MeetingToScopeWorkflow:
    """End-to-end meeting transcript processing and scope generation pipeline."""

    def __init__(
        self,
        storage: Optional[Task3Storage] = None,
        kb_client: Optional[KnowledgeBrainClient] = None,
        anthropic_client=None,
    ):
        self.storage = storage or Task3Storage()
        self.kb_client = kb_client or KnowledgeBrainClient()
        self.analyst = MeetingAnalyst(anthropic_client=anthropic_client)
        self.capability_analyst = CapabilityAnalyst(kb_client=self.kb_client)
        self.planner = ScopePlanner()
        self.proposal_writer = ProposalWriter()
        self.diff_engine = DiffEngine()

    async def process_initial_meeting(
        self,
        project_id: str,
        title: str,
        transcript_text: str,
        client_name: str = "Client",
        meeting_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process an initial client meeting transcript.
        Generates baseline scope v1.0, task breakdown, and proposal draft (in DRAFT status).
        """
        if not project_id or not project_id.strip():
            raise ValueError("project_id cannot be empty.")
        if not transcript_text or not transcript_text.strip():
            raise ValueError("Transcript text cannot be empty.")

        clean_pid = project_id.strip()
        clean_title = title.strip() or "Initial Discovery Meeting"
        clean_text = transcript_text.strip()

        # Step 1: Save transcript record
        transcript_id = f"TRN-{clean_pid}-init-{uuid.uuid4().hex[:6]}"
        transcript_record = MeetingTranscriptRecord(
            transcript_id=transcript_id,
            project_id=clean_pid,
            meeting_type="initial",
            title=clean_title,
            client_name=client_name,
            raw_text=clean_text,
            meeting_date=meeting_date or datetime.utcnow().strftime("%Y-%m-%d"),
            processed_at=datetime.utcnow(),
            model_used=settings.claude_model_primary if not settings.mock_llm else "mock-heuristic",
        )
        self.storage.save_transcript(transcript_record)

        # Step 2: Agent 1 - Extract requirements & objectives
        analysis_data = await self.analyst.analyze_transcript(
            transcript_text=clean_text,
            project_id=clean_pid,
            title=clean_title,
        )
        requirements = analysis_data["requirements"]

        # Step 3: Agent 2 - Query Knowledge Brain for capability assessments
        assessments = await self.capability_analyst.assess_requirements(requirements)

        # Step 4: Agent 3 - Generate Scope of Work & Task Estimates (v1.0)
        scope = self.planner.build_scope(
            project_id=clean_pid,
            project_title=clean_title,
            requirements=requirements,
            assessments=assessments,
            analysis_data=analysis_data,
            version="v1.0",
        )
        self.storage.save_scope(scope)

        # Step 5: Agent 4 - Write initial proposal draft (Status: DRAFT)
        proposal = self.proposal_writer.generate_draft(
            scope=scope,
            client_name=client_name,
        )
        self.storage.save_proposal(proposal)

        return {
            "project_id": clean_pid,
            "version": "v1.0",
            "transcript_id": transcript_id,
            "scope": scope,
            "proposal": proposal,
            "requirements_count": len(requirements),
            "total_estimated_hours": scope.total_estimated_hours,
            "status": "draft_created_awaiting_review",
        }

    async def process_followup_meeting(
        self,
        project_id: str,
        title: str,
        transcript_text: str,
        client_name: str = "Client",
        meeting_date: Optional[str] = None,
        new_version: str = "v2.0",
    ) -> Dict[str, Any]:
        """
        Process a follow-up client meeting transcript.
        Compares with baseline scope v1.0, detects changes, produces ChangeDetectionReport,
        and generates revised ScopeOfWork (v2.0) and revised ProposalDraft.
        """
        if not project_id or not project_id.strip():
            raise ValueError("project_id cannot be empty.")
        if not transcript_text or not transcript_text.strip():
            raise ValueError("Transcript text cannot be empty.")

        clean_pid = project_id.strip()
        clean_title = title.strip() or "Follow-up Scope Review"
        clean_text = transcript_text.strip()

        # Retrieve baseline scope
        baseline_scope = self.storage.get_scope(clean_pid, version="v1.0")
        if not baseline_scope:
            # Check latest available scope
            baseline_scope = self.storage.get_scope(clean_pid)
            if not baseline_scope:
                raise ValueError(
                    f"No baseline scope found for project '{clean_pid}'. "
                    "Process an initial meeting before submitting a follow-up."
                )

        # Step 1: Save follow-up transcript
        transcript_id = f"TRN-{clean_pid}-fol-{uuid.uuid4().hex[:6]}"
        transcript_record = MeetingTranscriptRecord(
            transcript_id=transcript_id,
            project_id=clean_pid,
            meeting_type="follow_up",
            title=clean_title,
            client_name=client_name,
            raw_text=clean_text,
            meeting_date=meeting_date or datetime.utcnow().strftime("%Y-%m-%d"),
            processed_at=datetime.utcnow(),
            model_used=settings.claude_model_primary if not settings.mock_llm else "mock-heuristic",
        )
        self.storage.save_transcript(transcript_record)

        # Step 2: Agent 1 - Extract new statements and requests
        followup_analysis = await self.analyst.analyze_transcript(
            transcript_text=clean_text,
            project_id=clean_pid,
            title=clean_title,
        )
        followup_reqs = followup_analysis["requirements"]

        # Step 3: Agent 2 - Check capability on any new requirements
        followup_assessments = await self.capability_analyst.assess_requirements(followup_reqs)

        # Step 4: Agent 5 (Diff Engine) - Compare baseline vs follow-up
        change_report, revised_scope, revised_proposal = self.diff_engine.detect_changes(
            baseline_scope=baseline_scope,
            followup_requirements=followup_reqs,
            followup_assessments=followup_assessments,
            followup_analysis_data=followup_analysis,
            new_version=new_version,
        )

        # Step 5: Mark previous proposal as SUPERSEDED if existing
        prev_proposals = self.storage.list_proposals(clean_pid)
        for prev in prev_proposals:
            if prev.scope_version != new_version and prev.status != ProposalStatus.SUPERSEDED:
                prev.status = ProposalStatus.SUPERSEDED
                prev.updated_at = datetime.utcnow()
                self.storage.save_proposal(prev)

        # Step 6: Save revised scope, change report, and revised proposal
        self.storage.save_scope(revised_scope)
        self.storage.save_change_report(change_report)
        self.storage.save_proposal(revised_proposal)

        return {
            "project_id": clean_pid,
            "baseline_version": baseline_scope.version,
            "revised_version": new_version,
            "transcript_id": transcript_id,
            "report_id": change_report.report_id,
            "change_report": change_report,
            "revised_scope": revised_scope,
            "revised_proposal": revised_proposal,
            "net_hour_delta": change_report.net_hour_delta,
            "status": "revised_draft_created_awaiting_review",
        }
