/**
 * Tests for Strict 20-Consecutive-Approval Autonomy Engine
 * and Quality-Drop Withdrawal
 */

import * as fs from 'fs';
import * as path from 'path';
import { AutonomyEngine } from '../src/services/autonomyEngine';
import { PersistentStore } from '../src/storage/persistentStore';
import { DraftReply } from '../src/models/types';
import { AgentConfig, loadConfig } from '../src/utils/config';

describe('AutonomyEngine', () => {
  const testDataDir = path.resolve(__dirname, '../data/test_autonomy');
  let store: PersistentStore;
  let engine: AutonomyEngine;
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
      maxAllowedEditRate: 0.2, // 20% max edits in window
      maxAllowedRejectionRate: 0.05, // 5% max rejections
      enableRealSending: false,
      logLevel: 'error',
      mockLlm: true,
      mockKb: true,
    });
    engine = new AutonomyEngine(store, testConfig);
  });

  afterAll(() => {
    if (fs.existsSync(testDataDir)) {
      fs.rmSync(testDataDir, { recursive: true, force: true });
    }
  });

  const dummyDraft = (category: any, humanReviewRequired = false, hasSources = true): DraftReply => ({
    id: 'd1',
    emailId: 'e1',
    category,
    proposedBody: 'Test response body with sufficient content.',
    supportingSources: hasSources
      ? [{ title: 'Doc', url: 'https://example.com', snippet: 'Guide', score: 0.9 }]
      : [],
    supportingImages: [],
    internalExplanation: 'Grounding explanation',
    uncertaintyWarnings: [],
    humanReviewRequired,
    autoSendEligible: true,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  });

  it('blocks automatic sending before 20 consecutive unedited approvals', async () => {
    const draft = dummyDraft('technical_support');

    // 19 consecutive approvals
    for (let i = 1; i <= 19; i++) {
      await engine.recordReview('technical_support', 'approve', `dec_${i}`);
      const state = engine.getCategoryState('technical_support');
      expect(state.consecutiveUneditedApprovals).toBe(i);
      expect(state.isAutonomous).toBe(false);

      const check = engine.canAutoSend('technical_support', draft);
      expect(check.allowed).toBe(false);
      expect(check.reason).toContain('has not reached 20 consecutive');
    }
  });

  it('enables autonomy on the 20th consecutive unedited approval for that category', async () => {
    const draft = dummyDraft('technical_support');

    for (let i = 1; i <= 20; i++) {
      await engine.recordReview('technical_support', 'approve', `dec_${i}`);
    }

    const state = engine.getCategoryState('technical_support');
    expect(state.consecutiveUneditedApprovals).toBe(20);
    expect(state.isAutonomous).toBe(true);
    expect(state.autonomyGrantedAt).toBeDefined();

    const check = engine.canAutoSend('technical_support', draft);
    expect(check.allowed).toBe(true);
  });

  it('tracks autonomy strictly per category and does not combine approvals across categories', async () => {
    // 20 approvals in technical_support
    for (let i = 1; i <= 20; i++) {
      await engine.recordReview('technical_support', 'approve', `dec_tech_${i}`);
    }

    // technical_support is autonomous, but billing_and_payments is NOT
    expect(engine.getCategoryState('technical_support').isAutonomous).toBe(true);
    expect(engine.getCategoryState('billing_and_payments').isAutonomous).toBe(false);
    expect(engine.getCategoryState('billing_and_payments').consecutiveUneditedApprovals).toBe(0);

    const billingDraft = dummyDraft('billing_and_payments');
    const check = engine.canAutoSend('billing_and_payments', billingDraft);
    expect(check.allowed).toBe(false);
  });

  it('resets streak to 0 when a draft is edited', async () => {
    for (let i = 1; i <= 15; i++) {
      await engine.recordReview('technical_support', 'approve', `dec_${i}`);
    }
    expect(engine.getCategoryState('technical_support').consecutiveUneditedApprovals).toBe(15);

    // 16th is edited
    await engine.recordReview('technical_support', 'edit', 'dec_edit_16');
    const state = engine.getCategoryState('technical_support');
    expect(state.consecutiveUneditedApprovals).toBe(0);
    expect(state.isAutonomous).toBe(false);
  });

  it('resets streak to 0 when a draft is rejected or regenerated', async () => {
    for (let i = 1; i <= 10; i++) {
      await engine.recordReview('technical_support', 'approve', `dec_${i}`);
    }

    await engine.recordReview('technical_support', 'reject', 'dec_rej');
    expect(engine.getCategoryState('technical_support').consecutiveUneditedApprovals).toBe(0);

    for (let i = 1; i <= 5; i++) {
      await engine.recordReview('technical_support', 'approve', `dec_b_${i}`);
    }
    expect(engine.getCategoryState('technical_support').consecutiveUneditedApprovals).toBe(5);

    await engine.recordReview('technical_support', 'regenerate', 'dec_regen');
    expect(engine.getCategoryState('technical_support').consecutiveUneditedApprovals).toBe(0);
  });

  it('persists autonomy state across store reload / application restarts', async () => {
    for (let i = 1; i <= 20; i++) {
      await engine.recordReview('account_and_login', 'approve', `dec_acc_${i}`);
    }
    expect(engine.getCategoryState('account_and_login').isAutonomous).toBe(true);

    // Reload state in a fresh PersistentStore and AutonomyEngine instance
    const newStore = new PersistentStore(testDataDir);
    const newEngine = new AutonomyEngine(newStore, testConfig);

    const reloadedState = newEngine.getCategoryState('account_and_login');
    expect(reloadedState.isAutonomous).toBe(true);
    expect(reloadedState.consecutiveUneditedApprovals).toBe(20);
    expect(reloadedState.autonomyGrantedAt).toBeDefined();
  });

  it('prevents duplicate review events from inflating the streak', async () => {
    await engine.recordReview('product_configuration', 'approve', 'same_decision_id');
    await engine.recordReview('product_configuration', 'approve', 'same_decision_id'); // Duplicate!

    const state = engine.getCategoryState('product_configuration');
    expect(state.consecutiveUneditedApprovals).toBe(1);
    expect(state.totalProcessed).toBe(1);
  });

  it('safely locks and handles concurrent review submissions sequentially', async () => {
    const promises = Array.from({ length: 10 }, (_, idx) =>
      engine.recordReview('feature_request', 'approve', `concurrent_dec_${idx}`)
    );
    await Promise.all(promises);

    const state = engine.getCategoryState('feature_request');
    expect(state.consecutiveUneditedApprovals).toBe(10);
    expect(state.totalProcessed).toBe(10);
  });

  it('withdraws autonomy when rolling window quality degrades (e.g. edit rate exceeds threshold)', async () => {
    // 1. Grant autonomy with 20 approvals
    for (let i = 1; i <= 20; i++) {
      await engine.recordReview('technical_support', 'approve', `dec_grant_${i}`);
    }
    expect(engine.getCategoryState('technical_support').isAutonomous).toBe(true);

    // 2. Submit edits in the rolling window (window size = 10, maxAllowedEditRate = 0.2 -> 2 edits out of 10)
    // 3 edits will trigger > 20% edit rate
    await engine.recordReview('technical_support', 'edit', 'dec_edit_1');
    await engine.recordReview('technical_support', 'edit', 'dec_edit_2');
    await engine.recordReview('technical_support', 'edit', 'dec_edit_3');

    const state = engine.getCategoryState('technical_support');
    expect(state.isAutonomous).toBe(false);
    expect(state.autonomyWithdrawnAt).toBeDefined();
    expect(state.autonomyWithdrawalReason).toContain('Threshold exceeded');
  });

  it('still blocks auto-sending even in autonomous category if draft has humanReviewRequired or no sources', async () => {
    // Grant autonomy
    for (let i = 1; i <= 20; i++) {
      await engine.recordReview('technical_support', 'approve', `dec_grant_${i}`);
    }
    expect(engine.getCategoryState('technical_support').isAutonomous).toBe(true);

    // Draft with humanReviewRequired: true
    const flaggedDraft = dummyDraft('technical_support', true, true);
    const check1 = engine.canAutoSend('technical_support', flaggedDraft);
    expect(check1.allowed).toBe(false);
    expect(check1.reason).toContain('Draft requires human review');

    // Draft with no supporting sources
    const noSourcesDraft = dummyDraft('technical_support', false, false);
    const check2 = engine.canAutoSend('technical_support', noSourcesDraft);
    expect(check2.allowed).toBe(false);
    expect(check2.reason).toContain('no supporting Knowledge Brain');
  });
});
