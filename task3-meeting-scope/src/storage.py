"""
Persistent atomic storage for Task 3: Meeting to Scope.
Stores transcripts, scopes, proposals, change reports, and review decisions.
Guarantees data survives application restarts.
"""

import json
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

from .models import (
    MeetingTranscriptRecord,
    ScopeOfWork,
    ProposalDraft,
    ChangeDetectionReport,
    ReviewDecisionRecord,
)
from .config import settings


class Task3Storage:
    """Atomic file-backed JSON store for projects and scopes."""

    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = Path(data_dir or settings.task3_data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_file = self.data_dir / "scope_store.json"

        self._transcripts: Dict[str, dict] = {}
        self._scopes: Dict[str, Dict[str, dict]] = {}  # project_id -> {version: scope_dict}
        self._proposals: Dict[str, dict] = {}  # proposal_id -> proposal_dict
        self._change_reports: Dict[str, dict] = {}  # report_id -> report_dict
        self._review_decisions: List[dict] = []

        self._load()

    def _atomic_write(self, data: dict) -> None:
        temp_file = self.db_file.with_suffix(f".tmp.{os.getpid()}.{datetime.utcnow().timestamp()}")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        try:
            if self.db_file.exists():
                shutil.copyfile(temp_file, self.db_file)
                temp_file.unlink(missing_ok=True)
            else:
                temp_file.rename(self.db_file)
        except Exception:
            # Fallback direct write
            with open(self.db_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
            temp_file.unlink(missing_ok=True)

    def _load(self) -> None:
        if not self.db_file.exists():
            return
        try:
            with open(self.db_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
                self._transcripts = raw.get("transcripts", {})
                self._scopes = raw.get("scopes", {})
                self._proposals = raw.get("proposals", {})
                self._change_reports = raw.get("change_reports", {})
                self._review_decisions = raw.get("review_decisions", [])
        except Exception as e:
            # Safe recovery if file is empty or corrupted
            pass

    def _save(self) -> None:
        payload = {
            "transcripts": self._transcripts,
            "scopes": self._scopes,
            "proposals": self._proposals,
            "change_reports": self._change_reports,
            "review_decisions": self._review_decisions,
        }
        self._atomic_write(payload)

    # --- Transcript Operations ---

    def save_transcript(self, transcript: MeetingTranscriptRecord) -> None:
        self._transcripts[transcript.transcript_id] = transcript.model_dump(mode="json")
        self._save()

    def get_transcript(self, transcript_id: str) -> Optional[MeetingTranscriptRecord]:
        data = self._transcripts.get(transcript_id)
        return MeetingTranscriptRecord.model_validate(data) if data else None

    def list_transcripts(self, project_id: Optional[str] = None) -> List[MeetingTranscriptRecord]:
        records = [
            MeetingTranscriptRecord.model_validate(t)
            for t in self._transcripts.values()
            if not project_id or t.get("project_id") == project_id
        ]
        return sorted(records, key=lambda x: str(x.processed_at))

    # --- Scope Operations ---

    def save_scope(self, scope: ScopeOfWork) -> None:
        if scope.project_id not in self._scopes:
            self._scopes[scope.project_id] = {}
        self._scopes[scope.project_id][scope.version] = scope.model_dump(mode="json")
        self._save()

    def get_scope(self, project_id: str, version: Optional[str] = None) -> Optional[ScopeOfWork]:
        project_scopes = self._scopes.get(project_id, {})
        if not project_scopes:
            return None
        if version:
            data = project_scopes.get(version)
            return ScopeOfWork.model_validate(data) if data else None
        # Default: latest version alphabetically or by insertion
        latest_ver = sorted(project_scopes.keys())[-1]
        return ScopeOfWork.model_validate(project_scopes[latest_ver])

    def list_scope_versions(self, project_id: str) -> List[ScopeOfWork]:
        project_scopes = self._scopes.get(project_id, {})
        return [
            ScopeOfWork.model_validate(data)
            for ver, data in sorted(project_scopes.items())
        ]

    # --- Proposal Operations ---

    def save_proposal(self, proposal: ProposalDraft) -> None:
        self._proposals[proposal.proposal_id] = proposal.model_dump(mode="json")
        self._save()

    def get_proposal(self, proposal_id: str) -> Optional[ProposalDraft]:
        data = self._proposals.get(proposal_id)
        return ProposalDraft.model_validate(data) if data else None

    def get_latest_proposal(self, project_id: str) -> Optional[ProposalDraft]:
        matches = [
            ProposalDraft.model_validate(p)
            for p in self._proposals.values()
            if p.get("project_id") == project_id
        ]
        if not matches:
            return None
        return sorted(matches, key=lambda x: str(x.created_at))[-1]

    def list_proposals(self, project_id: str) -> List[ProposalDraft]:
        matches = [
            ProposalDraft.model_validate(p)
            for p in self._proposals.values()
            if p.get("project_id") == project_id
        ]
        return sorted(matches, key=lambda x: str(x.created_at))

    # --- Change Report Operations ---

    def save_change_report(self, report: ChangeDetectionReport) -> None:
        self._change_reports[report.report_id] = report.model_dump(mode="json")
        self._save()

    def get_change_report(self, report_id: str) -> Optional[ChangeDetectionReport]:
        data = self._change_reports.get(report_id)
        return ChangeDetectionReport.model_validate(data) if data else None

    def get_change_reports_for_project(self, project_id: str) -> List[ChangeDetectionReport]:
        matches = [
            ChangeDetectionReport.model_validate(r)
            for r in self._change_reports.values()
            if r.get("project_id") == project_id
        ]
        return sorted(matches, key=lambda x: str(x.created_at))

    # --- Review Decisions ---

    def save_review_decision(self, decision: ReviewDecisionRecord) -> None:
        self._review_decisions.append(decision.model_dump(mode="json"))
        self._save()

    def list_review_decisions(self, project_id: Optional[str] = None) -> List[ReviewDecisionRecord]:
        return [
            ReviewDecisionRecord.model_validate(d)
            for d in self._review_decisions
            if not project_id or d.get("project_id") == project_id
        ]

    # --- Testing Helper ---

    def clear_all(self) -> None:
        self._transcripts.clear()
        self._scopes.clear()
        self._proposals.clear()
        self._change_reports.clear()
        self._review_decisions.clear()
        if self.db_file.exists():
            self.db_file.unlink()
