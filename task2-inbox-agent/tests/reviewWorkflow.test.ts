/**
 * Tests for Human Review Workflow Service
 */

import * as fs from 'fs';
import * as path from 'path';
import { ReviewService } from '../src/services/reviewService';
import { PersistentStore } from '../src/storage/persistentStore';
import { AutonomyEngine } from '../src/services/autonomyEngine';
import { EmailSender } from '../src/services/emailSender';
import { CustomerEmail, DraftReply } from '../src/models/types';
import { AgentConfig, loadConfig } from '../src/utils/config';

describe('ReviewService', () => {
  const testDataDir = path.resolve(__dirname, '../data/test_review');
  let store: PersistentStore;
  let autonomyEngine: AutonomyEngine;
  let emailSender: EmailSender;
  let reviewService: ReviewService;
  let testConfig: AgentConfig;

  beforeEach(() => {
    if (fs.existsSync(testDataDir)) {
      fs.rmSync(testDataDir, { recursive: true, force: true });
    }
    store = new PersistentStore(testDataDir);
    testConfig = loadConfig({
      port: 3001,
      kbTimeoutMs: 1000,
      autonomyStreakThreshold: 20,
      qualityWindowSize: 10,
      maxAllowedEditRate: 0.2,
      maxAllowedRejectionRate: 0.05,
      enableRealSending: false,
      logLevel: 'error',
      mockLlm: true,
      mockKb: true,
    });
    autonomyEngine = new AutonomyEngine(store, testConfig);
    emailSender = new EmailSender(store, autonomyEngine, testConfig);
    reviewService = new ReviewService(store, autonomyEngine, emailSender);
  });

  afterAll(() => {
    if (fs.existsSync(testDataDir)) {
      fs.rmSync(testDataDir, { recursive: true, force: true });
    }
  });

  function setupPendingReview(): { email: CustomerEmail; draft: DraftReply } {
    const email: CustomerEmail = {
      id: 'e_rev_1',
      senderEmail: 'customer@example.com',
      subject: 'Custom Domain Setup',
      body: 'How do I point my domain nameservers to Brilliant Directories?',
      receivedAt: new Date().toISOString(),
      status: 'awaiting_review',
      category: 'technical_support',
      draftId: 'd_rev_1',
    };

    const draft: DraftReply = {
      id: 'd_rev_1',
      emailId: 'e_rev_1',
      category: 'technical_support',
      proposedBody: 'Hello Customer,\nHere is the official guide to pointing your domain nameservers.',
      supportingSources: [
        {
          title: 'Domain Guide',
          url: 'https://support.bd.com/domain-setup',
          snippet: 'Point NS records.',
          score: 0.9,
        },
      ],
      supportingImages: [],
      internalExplanation: 'Grounded in documentation.',
      uncertaintyWarnings: [],
      humanReviewRequired: true,
      autoSendEligible: true,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };

    store.saveEmail(email);
    store.saveDraft(draft);
    return { email, draft };
  }

  it('approves draft without edits, updates streak and marks status sent', async () => {
    setupPendingReview();

    const result = await reviewService.processReview({
      draftId: 'd_rev_1',
      action: 'approve',
      reviewerName: 'Sarah Reviewer',
      sendOnApproval: true,
    });

    expect(result.decision.action).toBe('approve');
    expect(result.decision.reviewerName).toBe('Sarah Reviewer');
    expect(result.email.status).toBe('sent');
    expect(result.sentResult).toBeDefined();
    expect(result.sentResult?.simulated).toBe(true);

    // Verify streak incremented
    const autoState = autonomyEngine.getCategoryState('technical_support');
    expect(autoState.consecutiveUneditedApprovals).toBe(1);
  });

  it('edits draft before approving, saves finalBody, and resets streak', async () => {
    setupPendingReview();

    const editedText = 'Hello Customer,\nCustom personalized reply with specific guidance.';
    const result = await reviewService.processReview({
      draftId: 'd_rev_1',
      action: 'edit',
      editedBody: editedText,
      reviewerName: 'Dave Reviewer',
      reviewerFeedback: 'Added custom touch.',
    });

    expect(result.decision.action).toBe('edit');
    expect(result.draft.finalBody).toBe(editedText);
    expect(result.email.status).toBe('sent');
    expect(result.sentResult?.body).toBe(editedText);

    // Verify streak reset to 0
    const autoState = autonomyEngine.getCategoryState('technical_support');
    expect(autoState.consecutiveUneditedApprovals).toBe(0);
  });

  it('rejects draft and marks email rejected', async () => {
    setupPendingReview();

    const result = await reviewService.processReview({
      draftId: 'd_rev_1',
      action: 'reject',
      reviewerFeedback: 'Incorrect answer; do not send.',
    });

    expect(result.decision.action).toBe('reject');
    expect(result.email.status).toBe('rejected');
    expect(result.sentResult).toBeUndefined();

    // Streak reset to 0
    const autoState = autonomyEngine.getCategoryState('technical_support');
    expect(autoState.consecutiveUneditedApprovals).toBe(0);
  });

  it('escalates email to human expert', async () => {
    setupPendingReview();

    const result = await reviewService.processReview({
      draftId: 'd_rev_1',
      action: 'escalate',
      reviewerFeedback: 'Requires senior infrastructure engineering attention.',
    });

    expect(result.decision.action).toBe('escalate');
    expect(result.email.status).toBe('escalated');
    expect(result.draft.humanReviewRequired).toBe(true);
  });

  it('prevents re-reviewing an email that has already been sent', async () => {
    setupPendingReview();

    // First review: approve and send
    await reviewService.processReview({
      draftId: 'd_rev_1',
      action: 'approve',
      sendOnApproval: true,
    });

    // Second review attempt must fail
    await expect(
      reviewService.processReview({
        draftId: 'd_rev_1',
        action: 'approve',
      })
    ).rejects.toThrow(/already been sent/i);
  });

  it('records complete audit history accessible via getReviewHistory', async () => {
    setupPendingReview();

    await reviewService.processReview({
      draftId: 'd_rev_1',
      action: 'reject',
      reviewerFeedback: 'Testing audit trail.',
    });

    const history = reviewService.getReviewHistory('technical_support');
    expect(history.length).toBe(1);
    expect(history[0].category).toBe('technical_support');
    expect(history[0].reviewerFeedback).toBe('Testing audit trail.');
  });
});
