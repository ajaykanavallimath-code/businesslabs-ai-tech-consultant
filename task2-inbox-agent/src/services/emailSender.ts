/**
 * Safe email sending abstraction.
 * Defaults to simulated sending, preventing real customer emails from leaking.
 * Enforces pre-send safety checks and duplicate send prevention.
 */

import { CustomerEmail, DraftReply, SendResult } from '../models/types';
import { PersistentStore } from '../storage/persistentStore';
import { AgentConfig, config as globalConfig } from '../utils/config';
import { SafeLogger } from '../utils/logger';
import { AutonomyEngine } from './autonomyEngine';

export interface SendEmailOptions {
  email: CustomerEmail;
  draft: DraftReply;
  isHumanApproved?: boolean;
}

export class EmailSender {
  private store: PersistentStore;
  private autonomyEngine: AutonomyEngine;
  private config: AgentConfig;

  constructor(
    store: PersistentStore,
    autonomyEngine: AutonomyEngine,
    config?: AgentConfig
  ) {
    this.store = store;
    this.autonomyEngine = autonomyEngine;
    this.config = config || globalConfig;
  }

  /**
   * Attempt to send an email reply (either autonomously or following human approval).
   */
  async sendReply(options: SendEmailOptions): Promise<SendResult> {
    const { email, draft, isHumanApproved = false } = options;

    // 1. Check for Duplicate Send
    if (this.store.isAlreadySent(email.id)) {
      throw new Error(`Email ${email.id} has already been sent. Duplicate send prevented.`);
    }

    // 2. If NOT explicitly approved by a human, check strict autonomy prerequisites
    if (!isHumanApproved) {
      const autonomyCheck = this.autonomyEngine.canAutoSend(draft.category, draft);
      if (!autonomyCheck.allowed) {
        throw new Error(
          `Unauthorized auto-send attempt for email ${email.id}: ${autonomyCheck.reason}`
        );
      }
    }

    // 3. Ensure draft is not empty
    const bodyToSend = draft.finalBody || draft.proposedBody;
    if (!bodyToSend || bodyToSend.trim().length === 0) {
      throw new Error(`Cannot send empty email draft for email ${email.id}.`);
    }

    // 4. Safe Sending Simulation vs Real Provider
    const now = new Date().toISOString();
    const isSimulated = !this.config.enableRealSending;
    const providerName = isSimulated ? 'SimulatedSender' : 'ConfiguredSmtpProvider';

    if (isSimulated) {
      SafeLogger.info(
        `[SIMULATED SEND] To: ${email.senderEmail} | Subject: Re: ${email.subject} | Category: ${draft.category} | HumanApproved: ${isHumanApproved}`
      );
    } else {
      SafeLogger.warn(
        `[LIVE SEND] To: ${email.senderEmail} | Subject: Re: ${email.subject} | Provider: ${providerName}`
      );
      // Real provider implementation hook (disabled by default)
    }

    const result: SendResult = {
      emailId: email.id,
      draftId: draft.id,
      recipient: email.senderEmail,
      subject: `Re: ${email.subject}`,
      body: bodyToSend,
      sentAt: now,
      simulated: isSimulated,
      provider: providerName,
    };

    // Update state & audit log
    email.status = 'sent';
    this.store.saveEmail(email);
    this.store.logSent(result);

    return result;
  }
}
