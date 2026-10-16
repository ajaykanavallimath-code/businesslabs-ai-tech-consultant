/**
 * Central Inbox Agent orchestrating email intake, categorization,
 * Knowledge Brain retrieval, grounded drafting, and safe sending routing.
 */

import {
  CustomerEmail,
  DraftReply,
  EmailCategory,
  KnowledgeBrainResponse,
  ProcessingStatus,
  SendResult,
} from '../models/types';
import { PersistentStore } from '../storage/persistentStore';
import { EmailClassifier, ClassificationResult } from '../services/classifier';
import { KnowledgeBrainClient } from '../services/kbClient';
import { ReplyDrafter } from '../services/drafter';
import { AutonomyEngine } from '../services/autonomyEngine';
import { EmailSender } from '../services/emailSender';
import { AgentConfig, config as globalConfig } from '../utils/config';
import { SafeLogger } from '../utils/logger';

export interface EmailInput {
  id?: string;
  senderEmail: string;
  senderName?: string;
  subject: string;
  body: string;
  receivedAt?: string;
  metadata?: Record<string, unknown>;
}

export interface ProcessedEmailResult {
  email: CustomerEmail;
  draft: DraftReply;
  sent?: SendResult;
  autoSent: boolean;
}

export class InboxAgent {
  public store: PersistentStore;
  public classifier: EmailClassifier;
  public kbClient: KnowledgeBrainClient;
  public drafter: ReplyDrafter;
  public autonomyEngine: AutonomyEngine;
  public emailSender: EmailSender;
  public config: AgentConfig;

  constructor(dependencies?: {
    store?: PersistentStore;
    classifier?: EmailClassifier;
    kbClient?: KnowledgeBrainClient;
    drafter?: ReplyDrafter;
    autonomyEngine?: AutonomyEngine;
    emailSender?: EmailSender;
    config?: AgentConfig;
  }) {
    this.config = dependencies?.config || globalConfig;
    this.store = dependencies?.store || new PersistentStore();
    this.classifier = dependencies?.classifier || new EmailClassifier(this.config);
    this.kbClient = dependencies?.kbClient || new KnowledgeBrainClient(this.config);
    this.drafter = dependencies?.drafter || new ReplyDrafter(this.config);
    this.autonomyEngine =
      dependencies?.autonomyEngine || new AutonomyEngine(this.store, this.config);
    this.emailSender =
      dependencies?.emailSender ||
      new EmailSender(this.store, this.autonomyEngine, this.config);
  }

  /**
   * Ingest and process an incoming customer email.
   * Enforces deduplication, classification, KB context retrieval, drafting,
   * and autonomy check before deciding whether to auto-send or require human review.
   */
  async processEmail(input: EmailInput): Promise<ProcessedEmailResult> {
    const emailId =
      input.id || `email_${Date.now().toString(36)}_${Math.random().toString(36).substring(2, 7)}`;

    // 1. Deduplication / Idempotency Check
    const existingEmail = this.store.getEmail(emailId);
    if (existingEmail && existingEmail.draftId) {
      const existingDraft = this.store.getDraft(existingEmail.draftId);
      if (existingDraft) {
        SafeLogger.info(`Email ${emailId} already processed. Returning existing record.`);
        return {
          email: existingEmail,
          draft: existingDraft,
          autoSent: existingEmail.status === 'sent',
        };
      }
    }

    // 2. Validate Input
    if (!input.senderEmail || !input.subject) {
      const invalidEmail: CustomerEmail = {
        id: emailId,
        senderEmail: input.senderEmail || 'unknown@example.com',
        senderName: input.senderName,
        subject: input.subject || '(No Subject)',
        body: input.body || '',
        receivedAt: input.receivedAt || new Date().toISOString(),
        status: 'failed',
        category: 'other_or_uncertain',
        metadata: { error: 'Missing required email fields (senderEmail or subject).' },
      };
      this.store.saveEmail(invalidEmail);
      throw new Error(`Invalid email input: missing required fields for email ${emailId}`);
    }

    const email: CustomerEmail = {
      id: emailId,
      senderEmail: input.senderEmail.trim(),
      senderName: input.senderName?.trim(),
      subject: input.subject.trim(),
      body: (input.body || '').trim(),
      receivedAt: input.receivedAt || new Date().toISOString(),
      status: 'processing',
      metadata: input.metadata || {},
    };
    this.store.saveEmail(email);

    try {
      // 3. Step 1: Categorize Email
      SafeLogger.info(`Classifying email ${email.id}: "${email.subject}"`);
      const classification: ClassificationResult = await this.classifier.classify(email);
      email.category = classification.category;
      email.confidence = classification.confidence;

      // 4. Step 2: Query Knowledge Brain
      SafeLogger.info(`Querying Knowledge Brain for email ${email.id}`);
      let kbResponse: KnowledgeBrainResponse;
      try {
        kbResponse = await this.kbClient.query(
          `${email.subject}\n${email.body}`,
          3
        );
      } catch (err) {
        SafeLogger.warn(`Knowledge Brain lookup failed for email ${email.id}: ${(err as Error).message}`);
        kbResponse = {
          query: email.subject,
          answer: 'Documentation service unavailable.',
          confidence_score: 0.0,
          escalated: true,
          escalation_id: 'kb_failure',
          sources: [],
          images: [],
        };
      }

      // 5. Step 3: Draft Grounded Reply
      SafeLogger.info(`Drafting reply for email ${email.id}`);
      const draft: DraftReply = await this.drafter.draftReply(
        email,
        classification,
        kbResponse
      );

      // Link email and draft
      email.draftId = draft.id;

      // 6. Step 4: Evaluate Autonomy & Sending Gate
      let sentResult: SendResult | undefined;
      let autoSent = false;

      const autonomyCheck = this.autonomyEngine.canAutoSend(draft.category, draft);

      if (autonomyCheck.allowed) {
        SafeLogger.info(
          `[AUTONOMOUS SEND TRIGGERED] Category "${draft.category}" is autonomous. Sending reply.`
        );
        try {
          sentResult = await this.emailSender.sendReply({
            email,
            draft,
            isHumanApproved: false,
          });
          email.status = 'sent';
          autoSent = true;
        } catch (err) {
          SafeLogger.error(`Auto-send failed for email ${email.id}:`, err);
          email.status = 'failed';
        }
      } else {
        SafeLogger.info(
          `[HUMAN REVIEW REQUIRED] Email ${email.id} routed to review. Reason: ${autonomyCheck.reason}`
        );
        email.status = 'awaiting_review';
      }

      // 7. Persist final state
      this.store.saveEmail(email);
      this.store.saveDraft(draft);

      return {
        email,
        draft,
        sent: sentResult,
        autoSent,
      };
    } catch (error) {
      SafeLogger.error(`Error processing email ${email.id}:`, error);
      email.status = 'failed';
      this.store.saveEmail(email);
      throw error;
    }
  }

  /**
   * Batch process an array of emails in sequence.
   */
  async batchProcess(emails: EmailInput[]): Promise<ProcessedEmailResult[]> {
    const results: ProcessedEmailResult[] = [];
    for (const email of emails) {
      try {
        const result = await this.processEmail(email);
        results.push(result);
      } catch (err) {
        SafeLogger.error(`Failed to process email in batch: ${(err as Error).message}`);
      }
    }
    return results;
  }
}
