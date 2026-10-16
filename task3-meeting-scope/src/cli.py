"""
Interactive Command-Line Interface (CLI) for Task 3: Meeting to Scope.
Supports running discovery sessions, follow-ups, viewing scopes/proposals,
review approvals, and safe delivery checks from the terminal.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from .workflow import MeetingToScopeWorkflow
from .review_service import ReviewService
from .storage import Task3Storage


def parse_args():
    parser = argparse.ArgumentParser(
        prog="meeting-to-scope",
        description="BusinessLabs Task 3: Meeting to Scope CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Initial meeting command
    p_init = subparsers.add_parser("initial", help="Process an initial meeting transcript")
    p_init.add_argument("--project", "-p", required=True, help="Project identifier (e.g. PRJ-001)")
    p_init.add_argument("--title", "-t", default="Discovery Meeting", help="Meeting title")
    p_init.add_argument("--file", "-f", required=True, help="Path to transcript file")
    p_init.add_argument("--client", "-c", default="Client", help="Client name")

    # Follow-up meeting command
    p_fol = subparsers.add_parser("followup", help="Process a follow-up meeting transcript")
    p_fol.add_argument("--project", "-p", required=True, help="Project identifier (e.g. PRJ-001)")
    p_fol.add_argument("--title", "-t", default="Follow-up Meeting", help="Meeting title")
    p_fol.add_argument("--file", "-f", required=True, help="Path to transcript file")
    p_fol.add_argument("--client", "-c", default="Client", help="Client name")

    # Show project details
    p_show = subparsers.add_parser("show", help="Display scope and proposal details")
    p_show.add_argument("--project", "-p", required=True, help="Project identifier")
    p_show.add_argument("--version", "-v", default=None, help="Scope version (e.g. v1.0, v2.0)")

    # Approve proposal
    p_app = subparsers.add_parser("approve", help="Approve a proposal draft")
    p_app.add_argument("--proposal", required=True, help="Proposal ID")
    p_app.add_argument("--reviewer", "-r", required=True, help="Reviewer name")
    p_app.add_argument("--comments", "-m", default="Approved via CLI", help="Approval comments")

    # Reject proposal
    p_rej = subparsers.add_parser("reject", help="Reject a proposal draft")
    p_rej.add_argument("--proposal", required=True, help="Proposal ID")
    p_rej.add_argument("--reviewer", "-r", required=True, help="Reviewer name")
    p_rej.add_argument("--reason", required=True, help="Rejection reason")

    # Deliver proposal
    p_del = subparsers.add_parser("deliver", help="Attempt proposal delivery to client")
    p_del.add_argument("--proposal", required=True, help="Proposal ID")
    p_del.add_argument("--recipient", required=True, help="Client email address")
    p_del.add_argument("--delivered-by", default="CLI User", help="Sender identifier")

    return parser.parse_args()


async def main_async():
    args = parse_args()
    storage = Task3Storage()
    workflow = MeetingToScopeWorkflow(storage=storage)
    review_service = ReviewService(storage=storage)

    if args.command == "initial":
        path = Path(args.file)
        if not path.exists():
            print(f"Error: Transcript file '{args.file}' does not exist.")
            sys.exit(1)
        raw_text = path.read_text(encoding="utf-8")
        print(f"[*] Processing initial meeting for project '{args.project}'...")
        res = await workflow.process_initial_meeting(
            project_id=args.project,
            title=args.title,
            transcript_text=raw_text,
            client_name=args.client,
        )
        scope = res["scope"]
        proposal = res["proposal"]
        print("\n=== Initial Discovery Scope Generated ===")
        print(f"Project ID:              {res['project_id']}")
        print(f"Scope Version:           {res['version']}")
        print(f"Requirements Extracted:  {res['requirements_count']}")
        print(f"Total Estimated Hours:   {scope.total_estimated_hours:.1f} hrs")
        print(f"Proposal ID:             {proposal.proposal_id}")
        print(f"Proposal Status:         {proposal.status.value.upper()} (Approval Required)")
        print("\nScope Tasks:")
        for t in scope.tasks:
            print(f"  [{t.task_id}] {t.title} ({t.work_type.value}) - {t.estimated_hours} hrs [Conf: {t.confidence.value}]")

    elif args.command == "followup":
        path = Path(args.file)
        if not path.exists():
            print(f"Error: Transcript file '{args.file}' does not exist.")
            sys.exit(1)
        raw_text = path.read_text(encoding="utf-8")
        print(f"[*] Processing follow-up meeting for project '{args.project}'...")
        res = await workflow.process_followup_meeting(
            project_id=args.project,
            title=args.title,
            transcript_text=raw_text,
            client_name=args.client,
        )
        report = res["change_report"]
        rev_scope = res["revised_scope"]
        rev_prop = res["revised_proposal"]
        print("\n=== Change Detection Report & Revised Scope ===")
        print(f"Project ID:              {res['project_id']}")
        print(f"Baseline Version:        {res['baseline_version']} ({report.total_original_hours:.1f} hrs)")
        print(f"Revised Version:         {res['revised_version']} ({report.total_revised_hours:.1f} hrs)")
        print(f"Net Hour Delta:          {report.net_hour_delta:+.1f} hrs")
        print(f"Total Changes Detected:  {len(report.changes)}")
        print(f"Out of Scope Items:      {len(report.out_of_scope_requests)}")
        print(f"Revised Proposal ID:     {rev_prop.proposal_id} [{rev_prop.status.value.upper()}]")
        print("\nClassified Changes:")
        for c in report.changes:
            print(f"  [{c.change_id}] {c.classification.value.upper()}: {c.reason} (Delta: {c.hour_delta:+.1f} hrs)")

    elif args.command == "show":
        scope = storage.get_scope(args.project, version=args.version)
        if not scope:
            print(f"No scope found for project '{args.project}'.")
            sys.exit(1)
        proposal = storage.get_latest_proposal(args.project)
        print(f"\n=== Project: {args.project} ({scope.version}) ===")
        print(f"Title:         {scope.project_title}")
        print(f"Total Hours:   {scope.total_estimated_hours:.1f} hrs")
        print(f"Requirements:  {len(scope.requirements)}")
        if proposal:
            print(f"Proposal:      {proposal.proposal_id} [{proposal.status.value.upper()}] (Delivered: {proposal.delivered_to_client})")

    elif args.command == "approve":
        prop = review_service.approve_proposal(
            proposal_id=args.proposal,
            reviewer_id=args.reviewer,
            comments=args.comments,
        )
        print(f"[OK] Proposal '{prop.proposal_id}' successfully APPROVED by {prop.reviewer_id} at {prop.approved_at}.")

    elif args.command == "reject":
        prop = review_service.reject_proposal(
            proposal_id=args.proposal,
            reviewer_id=args.reviewer,
            rejection_reason=args.reason,
        )
        print(f"[OK] Proposal '{prop.proposal_id}' marked REJECTED by {prop.reviewer_id}. Reason: {prop.rejection_reason}")

    elif args.command == "deliver":
        try:
            res = review_service.deliver_proposal(
                proposal_id=args.proposal,
                recipient_email=args.recipient,
                delivered_by=args.delivered_by,
            )
            print(f"[SUCCESS] {res['message']}")
            print(f"Delivery Timestamp: {res['delivery_timestamp']}")
        except PermissionError as e:
            print(f"[BLOCKED] Delivery Gate Violated: {e}")
            sys.exit(2)
        except Exception as e:
            print(f"[ERROR] {e}")
            sys.exit(1)


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
