/**
 * Tests for Safe Email Sending Abstraction and Pre-Send Safety Gates
 */

import * as fs from 'fs';
import * as path from 'path';
import { EmailSender } from '../src/services/emailSender';
import { PersistentStore } from '../src/storage/persistentStore';
import { AutonomyEngine } from '../src/services/autonomyEngine';
import { CustomerEmail, DraftReply } from '../src/models/types';
import { AgentConfig, loadConfig } from '../src/utils/config';

describe('EmailSender Safety Gates', () => {
  const testDataDir = path.resolve(__dirname, '../data/test_sending');
  let store: PersistentStore;
  let autonomyEngine: AutonomyEngine;
  let sender: EmailSender;
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
      enableRealSending: false, // Safe simulated default
      logLevel: 'error',
      mockLlm: true,
      mockKb: true,
    });
    autonomyEngine = new AutonomyEngine(store, testConfig);
    sender = new EmailSender(store, autonomyEngine, testConfig);
  });

  afterAll(() => {
    if (fs.existsSync(testDataDir)) {
      fs.rmSync(testDataDir, { recursive: true, force: true });
    }
  });

  const makeEmailAndDraft = (): { email: CustomerEmail; draft: DraftReply } => {
    const email: CustomerEmail = {
      id: 'e_send_1',
      senderEmail: 'recipient@client.com',
      subject: 'Question on DNS',
      body: 'Need help with DNS.',
      receivedAt: new Date().toISOString(),
      status: 'awaiting_review',
      category: 'technical_support',
      draftId: 'd_send_1',
    };
    const draft: DraftReply = {
      id: 'd_send_1',
      emailId: 'e_send_1',
      category: 'technical_support',
      proposedBody: 'Here are the DNS steps...',
      supportingSources: [
        { title: 'DNS Guide', url: 'https://bd.com/dns', snippet: 'Nameservers', score: 0.9 },
      ],
      supportingImages: [],
      internalExplanation: 'Grounded in documentation.',
      uncertaintyWarnings: [],
      humanReviewRequired: false,
      autoSendEligible: true,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };
    store.saveEmail(email);
    store.saveDraft(draft);
    return { email, draft };
  };

  it('defaults to simulated sending mode and logs simulated result', async () => {
    const { email, draft } = makeEmailAndDraft();

    const result = await sender.sendReply({
      email,
      draft,
      isHumanApproved: true,
    });

    expect(result.simulated).toBe(true);
    expect(result.provider).toBe('SimulatedSender');
    expect(result.recipient).toBe(email.senderEmail);
    expect(result.emailId).toBe(email.id);
    expect(store.isAlreadySent(email.id)).toBe(true);
  });

  it('blocks autonomous sending when category is not yet autonomous', async () => {
    const { email, draft } = makeEmailAndDraft();

    // isHumanApproved = false, streak = 0 -> MUST throw
    await expect(
      sender.sendReply({
        email,
        draft,
        isHumanApproved: false,
      })
    ).rejects.toThrow(/Unauthorized auto-send attempt/i);
  });

  it('prevents duplicate sends for the same email ID', async () => {
    const { email, draft } = makeEmailAndDraft();

    await sender.sendReply({
      email,
      draft,
      isHumanApproved: true,
    });

    // Try sending again
    await expect(
      sender.sendReply({
        email,
        draft,
        isHumanApproved: true,
      })
    ).rejects.toThrow(/has already been sent/i);
  });

  it('rejects sending when draft body is empty', async () => {
    const { email, draft } = makeEmailAndDraft();
    draft.proposedBody = '   ';
    draft.finalBody = undefined;

    await expect(
      sender.sendReply({
        email,
        draft,
        isHumanApproved: true,
      })
    ).rejects.toThrow(/empty email draft/i);
  });
});
