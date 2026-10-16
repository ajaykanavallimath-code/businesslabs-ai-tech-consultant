"""
Agent 5 / Diff Engine: Change Detection & Version Evolution.
Compares a follow-up meeting against the baseline scope of work.
Classifies changes into: unchanged, clarified, modified, added, removed, out_of_scope, needs_clarification.
Computes hour deltas, preserves baseline scope v1.0, generates revised scope v2.0 and proposal draft.
"""

from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime

from ..models import (
    ScopeOfWork,
    ExtractedRequirement,
    CapabilityAssessment,
    CapabilityStatus,
    TaskEstimate,
    ChangeItem,
    ChangeDetectionReport,
    RequirementStatus,
    RequirementCertainty,
    ProposalDraft,
    WorkType,
    EstimateConfidence,
)
from .planner import ScopePlanner
from .proposal import ProposalWriter


class DiffEngine:
    """Compares baseline scope with follow-up meeting data and generates revised scopes."""

    def __init__(self):
        self.planner = ScopePlanner()
        self.proposal_writer = ProposalWriter()

    def detect_changes(
        self,
        baseline_scope: ScopeOfWork,
        followup_requirements: List[ExtractedRequirement],
        followup_assessments: List[CapabilityAssessment],
        followup_analysis_data: Dict[str, Any],
        new_version: str = "v2.0",
    ) -> Tuple[ChangeDetectionReport, ScopeOfWork, ProposalDraft]:
        """
        Compare baseline scope with follow-up extracted requirements.
        Produce a ChangeDetectionReport, a revised ScopeOfWork (new_version), and a revised ProposalDraft.
        """
        changes: List[ChangeItem] = []
        out_of_scope_items: List[ChangeItem] = []
        change_idx = 1

        baseline_reqs_by_id = {r.id: r for r in baseline_scope.requirements}
        matched_baseline_ids = set()

        # Track revised requirements list
        revised_requirements: List[ExtractedRequirement] = []
        revised_assessments: List[CapabilityAssessment] = list(baseline_scope.capability_assessments)
        baseline_ass_by_id = {a.requirement_id: a for a in baseline_scope.capability_assessments}
        followup_ass_by_id = {a.requirement_id: a for a in followup_assessments}

        for f_req in followup_requirements:
            # Check for match against baseline requirements
            best_match: Optional[ExtractedRequirement] = None
            f_title_lower = f_req.title.lower()

            # First match by explicit ID or title keywords
            if f_req.id in baseline_reqs_by_id:
                best_match = baseline_reqs_by_id[f_req.id]
            else:
                for b_id, b_req in baseline_reqs_by_id.items():
                    b_title_lower = b_req.title.lower()
                    # Check semantic overlap
                    words_b = set(b_title_lower.split())
                    words_f = set(f_title_lower.split())
                    common = words_b.intersection(words_f) - {"and", "or", "the", "for", "with", "in", "to", "a"}
                    if len(common) >= 2 or any(k in f_title_lower and k in b_title_lower for k in ("stripe", "member", "payment", "search", "directory", "brand", "design")):
                        best_match = b_req
                        break

            # Handle Out of Scope cases (e.g., native mobile apps, custom ERP, WordPress plugin engine)
            if any(k in f_title_lower for k in ("mobile app", "app store", "google play", "wordpress plugin", "hipaa", "patient medical")):
                chg = ChangeItem(
                    change_id=f"CHG-{change_idx:03d}",
                    classification=RequirementStatus.OUT_OF_SCOPE,
                    original_requirement_id=best_match.id if best_match else None,
                    original_text=best_match.description if best_match else None,
                    revised_text=f_req.description,
                    transcript_evidence=f_req.transcript_evidence or "Follow-up transcript statement.",
                    reason=(
                        f"Request '{f_req.title}' exceeds Brilliant Directories core capabilities "
                        "and requires third-party architecture or separate engagement."
                    ),
                    hour_delta=0.0,
                    new_risks=["Exceeds platform capabilities and project boundaries."],
                    human_approval_required=True,
                )
                out_of_scope_items.append(chg)
                changes.append(chg)
                change_idx += 1
                continue

            # Classify based on match and content
            if best_match:
                matched_baseline_ids.add(best_match.id)

                # Check if this clarifies an earlier ambiguous requirement
                if best_match.status == RequirementStatus.NEEDS_CLARIFICATION and f_req.status != RequirementStatus.NEEDS_CLARIFICATION:
                    f_req.status = RequirementStatus.CLARIFIED
                    f_req.certainty = RequirementCertainty.EXPLICIT_FACT
                    chg = ChangeItem(
                        change_id=f"CHG-{change_idx:03d}",
                        classification=RequirementStatus.CLARIFIED,
                        original_requirement_id=best_match.id,
                        original_text=best_match.description,
                        revised_text=f_req.description,
                        transcript_evidence=f_req.transcript_evidence or "Clarified in follow-up meeting.",
                        reason=f"Client clarified previous uncertainty regarding '{best_match.title}'.",
                        hour_delta=0.0,
                        new_dependencies=[],
                        new_risks=[],
                        human_approval_required=True,
                    )
                    changes.append(chg)
                    change_idx += 1
                    revised_requirements.append(f_req)

                # Check if requirement was removed / cancelled
                elif any(w in f_req.description.lower() for w in ("cancel", "remove", "drop", "no longer need", "omit")):
                    f_req.status = RequirementStatus.REMOVED
                    chg = ChangeItem(
                        change_id=f"CHG-{change_idx:03d}",
                        classification=RequirementStatus.REMOVED,
                        original_requirement_id=best_match.id,
                        original_text=best_match.description,
                        revised_text=f_req.description,
                        transcript_evidence=f_req.transcript_evidence or "Removed in follow-up meeting.",
                        reason=f"Client explicitly removed requirement '{best_match.title}'.",
                        hour_delta=-4.0,
                        new_dependencies=[],
                        new_risks=[],
                        human_approval_required=True,
                    )
                    changes.append(chg)
                    change_idx += 1

                # Check if requirement was modified (expanded or changed)
                elif best_match.description.strip() != f_req.description.strip():
                    f_req.status = RequirementStatus.MODIFIED
                    chg = ChangeItem(
                        change_id=f"CHG-{change_idx:03d}",
                        classification=RequirementStatus.MODIFIED,
                        original_requirement_id=best_match.id,
                        original_text=best_match.description,
                        revised_text=f_req.description,
                        transcript_evidence=f_req.transcript_evidence or "Modified in follow-up meeting.",
                        reason=f"Client modified specifications for '{best_match.title}'.",
                        hour_delta=3.5,
                        new_dependencies=[best_match.id],
                        new_risks=["Potential schedule impact due to scope expansion."],
                        human_approval_required=True,
                    )
                    changes.append(chg)
                    change_idx += 1
                    revised_requirements.append(f_req)
                    if f_req.id in followup_ass_by_id:
                        revised_assessments.append(followup_ass_by_id[f_req.id])
                    elif best_match.id in baseline_ass_by_id:
                        base_ass = baseline_ass_by_id[best_match.id]
                        revised_assessments.append(base_ass.model_copy(update={"requirement_id": f_req.id}))

                else:
                    # Unchanged
                    f_req.status = RequirementStatus.CONFIRMED
                    chg = ChangeItem(
                        change_id=f"CHG-{change_idx:03d}",
                        classification=RequirementStatus.CONFIRMED,
                        original_requirement_id=best_match.id,
                        original_text=best_match.description,
                        revised_text=f_req.description,
                        transcript_evidence=f_req.transcript_evidence or "Reaffirmed in follow-up.",
                        reason=f"Requirement '{best_match.title}' reaffirmed without modification.",
                        hour_delta=0.0,
                        new_dependencies=[],
                        new_risks=[],
                        human_approval_required=False,
                    )
                    changes.append(chg)
                    change_idx += 1
                    revised_requirements.append(best_match)

            else:
                # Brand new added requirement within platform scope
                f_req.status = RequirementStatus.ADDED
                chg = ChangeItem(
                    change_id=f"CHG-{change_idx:03d}",
                    classification=RequirementStatus.ADDED,
                    original_requirement_id=None,
                    original_text=None,
                    revised_text=f_req.description,
                    transcript_evidence=f_req.transcript_evidence or "Introduced in follow-up meeting.",
                    reason=f"New requirement added: '{f_req.title}'.",
                    hour_delta=5.0,
                    new_dependencies=["TSK-001"],
                    new_risks=["Additional configuration effort."],
                    human_approval_required=True,
                )
                changes.append(chg)
                change_idx += 1
                revised_requirements.append(f_req)
                if f_req.id in followup_ass_by_id:
                    revised_assessments.append(followup_ass_by_id[f_req.id])

        # Add any unreferenced baseline requirements as preserved
        for b_id, b_req in baseline_reqs_by_id.items():
            if b_id not in matched_baseline_ids and b_req not in revised_requirements:
                revised_requirements.append(b_req)

        # Merge analysis data
        merged_analysis = {
            "client_objectives": list(dict.fromkeys(
                baseline_scope.client_objectives + followup_analysis_data.get("client_objectives", [])
            )),
            "current_workflow": baseline_scope.current_workflow_summary,
            "assumptions": list(dict.fromkeys(
                baseline_scope.assumptions + followup_analysis_data.get("assumptions", [])
            )),
            "exclusions": list(dict.fromkeys(
                baseline_scope.exclusions + followup_analysis_data.get("exclusions", [])
            )),
            "risks": list(dict.fromkeys(
                baseline_scope.technical_risks + followup_analysis_data.get("risks", [])
            )),
        }

        # Build revised Scope of Work (v2.0)
        revised_scope = self.planner.build_scope(
            project_id=baseline_scope.project_id,
            project_title=baseline_scope.project_title,
            requirements=revised_requirements,
            assessments=revised_assessments,
            analysis_data=merged_analysis,
            version=new_version,
        )

        # Build revised Proposal Draft
        revised_proposal = self.proposal_writer.generate_draft(
            scope=revised_scope,
            client_name="Client",
        )

        # Compute hour deltas
        total_orig_hours = baseline_scope.total_estimated_hours
        total_rev_hours = revised_scope.total_estimated_hours
        net_delta = round(total_rev_hours - total_orig_hours, 2)

        summary_text = (
            f"Follow-up meeting comparison complete. Detected {len(changes)} change items "
            f"({len([c for c in changes if c.classification == RequirementStatus.MODIFIED])} modified, "
            f"{len([c for c in changes if c.classification == RequirementStatus.ADDED])} added, "
            f"{len([c for c in changes if c.classification == RequirementStatus.REMOVED])} removed, "
            f"{len(out_of_scope_items)} out of scope). "
            f"Original scope effort: {total_orig_hours:.1f} hrs; Revised scope effort: {total_rev_hours:.1f} hrs "
            f"(Net Delta: {net_delta:+.1f} hrs). Human approval required before delivery."
        )

        report = ChangeDetectionReport(
            report_id=f"CDR-{baseline_scope.project_id}-{baseline_scope.version}-to-{new_version}",
            project_id=baseline_scope.project_id,
            original_version=baseline_scope.version,
            follow_up_version=new_version,
            summary=summary_text,
            total_original_hours=total_orig_hours,
            total_revised_hours=total_rev_hours,
            net_hour_delta=net_delta,
            changes=changes,
            out_of_scope_requests=out_of_scope_items,
            created_at=datetime.utcnow(),
        )

        return report, revised_scope, revised_proposal
