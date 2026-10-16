/**
 * Command-Line Interface (CLI) for Task 2: Inbox Agent.
 * Allows viewing queue status, drafts awaiting review, approving/editing drafts,
 * and inspecting autonomy streaks and metrics directly from the terminal.
 */

import { InboxAgent } from './agents/inboxAgent';
import { ReviewService } from './services/reviewService';
import { ReviewAction } from './models/types';
import { SafeLogger } from './utils/logger';

async function main() {
  const args = process.argv.slice(2);
  const command = args[0] || 'help';

  const agent = new InboxAgent();
  const reviewService = new ReviewService(
    agent.store,
    agent.autonomyEngine,
    agent.emailSender,
    agent.drafter,
    agent.kbClient
  );

  switch (command) {
    case 'status': {
      console.log('\n=== TASK 2: INBOX AGENT STATUS ===');
      const metrics = agent.autonomyEngine.computeMetrics();
      console.log(`Total Emails:          ${metrics.totalEmails}`);
      console.log(`Total Drafts:          ${metrics.totalDrafts}`);
      console.log(`Drafts Awaiting Review:${metrics.totalAwaitingReview}`);
      console.log(`Total Emails Sent:     ${metrics.totalSent}`);
      console.log(`Total Escalated:       ${metrics.totalEscalated}`);
      console.log('\n--- Category Autonomy Status (20 Consecutive Approvals Rule) ---');
      for (const [cat, data] of Object.entries(metrics.categories)) {
        const autoBadge = data.isAutonomous ? ' [AUTONOMOUS]' : ' [HUMAN REVIEW REQUIRED]';
        console.log(
          `• ${cat.padEnd(23)}: Streak = ${data.consecutiveUneditedApprovals}/20 | Appr: ${(data.approvalRate * 100).toFixed(0)}% | Edit: ${(data.editRate * 100).toFixed(0)}% | Rej: ${(data.rejectionRate * 100).toFixed(0)}%${autoBadge}`
        );
        if (data.withdrawalReason) {
          console.log(`    ↳ Autonomy Withdrawn: ${data.withdrawalReason}`);
        }
      }
      console.log('=================================\n');
      break;
    }

    case 'queue':
    case 'drafts': {
      const awaiting = reviewService.listDraftsAwaitingReview();
      console.log(`\n=== DRAFTS AWAITING HUMAN REVIEW (${awaiting.length}) ===`);
      if (awaiting.length === 0) {
        console.log('No drafts currently awaiting human review.\n');
        return;
      }

      for (const d of awaiting) {
        const email = agent.store.getEmail(d.emailId);
        console.log(`\n------------------------------------------------------------`);
        console.log(`Draft ID:   ${d.id}`);
        console.log(`Email ID:   ${d.emailId}`);
        console.log(`Sender:     ${email?.senderEmail || 'N/A'}`);
        console.log(`Subject:    ${email?.subject || 'N/A'}`);
        console.log(`Category:   ${d.category}`);
        console.log(`Created:    ${d.createdAt}`);
        console.log(`Proposed Reply Preview:`);
        console.log(d.proposedBody.substring(0, 200) + '...\n');
        console.log(`Supporting Sources: ${d.supportingSources?.length || 0}`);
        for (const s of d.supportingSources || []) {
          console.log(`  - [${s.title}] (${s.url})`);
        }
      }
      console.log('------------------------------------------------------------\n');
      break;
    }

    case 'review': {
      const draftId = args[1];
      const action = args[2] as ReviewAction;
      const feedback = args[3];

      if (!draftId || !action) {
        console.error('Usage: npm run cli -- review <draftId> <approve|edit|reject|regenerate|escalate> [feedback/editedText]');
        process.exit(1);
      }

      try {
        const result = await reviewService.processReview({
          draftId,
          action,
          editedBody: action === 'edit' ? feedback : undefined,
          reviewerFeedback: action !== 'edit' ? feedback : undefined,
          reviewerName: 'CLI Reviewer',
        });
        console.log(`\n✓ Successfully processed review for draft ${draftId}: [Action: ${action}]`);
        console.log(`New Email Status: ${result.email.status}`);
        if (result.sentResult) {
          console.log(`Email Sent (${result.sentResult.simulated ? 'SIMULATED' : 'LIVE'}): To ${result.sentResult.recipient}`);
        }
      } catch (err) {
        console.error(`✗ Error reviewing draft: ${(err as Error).message}`);
        process.exit(1);
      }
      break;
    }

    case 'ingest': {
      const sender = args[1] || 'test.user@example.com';
      const subject = args[2] || 'Question about membership plans';
      const body =
        args[3] || 'Hi, how do I configure recurring payments on my membership plans? Thanks!';

      console.log(`Ingesting test email from ${sender}...`);
      const result = await agent.processEmail({
        senderEmail: sender,
        subject,
        body,
      });

      console.log('\n✓ Email processed successfully:');
      console.log(`Email ID:  ${result.email.id}`);
      console.log(`Draft ID:  ${result.draft.id}`);
      console.log(`Category:  ${result.draft.category}`);
      console.log(`Status:    ${result.email.status}`);
      console.log(`Auto-Sent: ${result.autoSent ? 'YES' : 'NO'}`);
      console.log(`Proposed Reply:`);
      console.log(result.draft.proposedBody);
      break;
    }

    default:
      console.log('\n=== TASK 2: INBOX AGENT CLI ===');
      console.log('Commands:');
      console.log('  status                         View agent metrics and category autonomy streaks');
      console.log('  drafts                         List drafts currently awaiting human review');
      console.log('  review <id> <action> [text]    Review a draft (approve, edit, reject, regenerate, escalate)');
      console.log('  ingest [email] [subj] [body]   Submit a test customer email for processing');
      console.log('===============================\n');
      break;
  }
}

if (require.main === module) {
  main().catch((err) => {
    console.error('Fatal CLI Error:', err);
    process.exit(1);
  });
}
