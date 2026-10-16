/**
 * Human review workflow service.
 * Manages approval, editing, rejection, regeneration, and escalation of customer drafts.
 * Persists review audit records, updates email statuses, and drives the autonomy engine.
 */

import {
  CustomerEmail,
  DraftReply,
  EmailCategory,
  KnowledgeBrainResponse,
  KnowledgeBrainSource,
  ReviewAction,
  ReviewDecision,
  SendResult,
} from '../models/types';
import { PersistentStore } from '../storage/persistentStore';
import { AutonomyEngine } from './autonomyEngine';
import { EmailSender } from './emailSender';
import { ReplyDrafter } from './drafter';
import { KnowledgeBrainClient } from './kbClient';
import { SafeLogger } from '../utils/logger';

export interface ReviewDraftInput {
  decisionId?: string;
  draftId: string;
  action: ReviewAction;
  editedBody?: string;
  reviewerFeedback?: string;
  reviewerName?: string;
  sendOnApproval?: boolean;
}

export interface ReviewDraftResult {
  decision: ReviewDecision;
  email: CustomerEmail;
  draft: DraftReply;
  sentResult?: SendResult;
}

export interface ReviewItemDetails {
  email: CustomerEmail;
  draft: DraftReply;
  sources: KnowledgeBrainSource[];
  isCategoryAutonomous: boolean;
  consecutiveApprovals: number;
}

export class ReviewService {
  private store: PersistentStore;
  private autonomyEngine: AutonomyEngine;
  private emailSender: EmailSender;
  private drafter?: ReplyDrafter;
  private kbClient?: KnowledgeBrainClient;

  constructor(
    store: PersistentStore,
    autonomyEngine: AutonomyEngine,
    emailSender: EmailSender,
    drafter?: ReplyDrafter,
    kbClient?: KnowledgeBrainClient
  ) {
    this.store = store;
    this.autonomyEngine = autonomyEngine;
    this.emailSender = emailSender;
    this.drafter = drafter;
    this.kbClient = kbClient;
  }

  /**
   * Fetch complete details for a draft awaiting review.
   */
  getReviewItem(draftId: string): ReviewItemDetails {
    const draft = this.store.getDraft(draftId);
    if (!draft) {
      throw new Error(`Draft ${draftId} not found.`);
    }

    const email = this.store.getEmail(draft.emailId);
    if (!email) {
      throw new Error(`Customer email for draft ${draftId} (id: ${draft.emailId}) not found.`);
    }

    const autonomyState = this.autonomyEngine.getCategoryState(draft.category);

    return {
      email,
      draft,
      sources: draft.supportingSources || [],
      isCategoryAutonomous: autonomyState.isAutonomous,
      consecutiveApprovals: autonomyState.consecutiveUneditedApprovals,
    };
  }

  /**
   * Process a human review decision (approve, edit, reject, regenerate, escalate).
   */
  async processReview(input: ReviewDraftInput): Promise<ReviewDraftResult> {
    const {
      draftId,
      action,
      editedBody,
      reviewerFeedback,
      reviewerName = 'Human Reviewer',
      sendOnApproval = true,
    } = input;

    const draft = this.store.getDraft(draftId);
    if (!draft) {
      throw new Error(`Draft ${draftId} not found.`);
    }

    const email = this.store.getEmail(draft.emailId);
    if (!email) {
      throw new Error(`Customer email ${draft.emailId} not found.`);
    }

    // Guard against re-reviewing already sent emails
    if (email.status === 'sent') {
      throw new Error(`Email ${email.id} has already been sent. Cannot review again.`);
    }

    const decisionId =
      input.decisionId ||
      `decision_${Date.now().toString(36)}_${Math.random().toString(36).substring(2, 7)}`;
    const previousDraftBody = draft.proposedBody;
    let finalDraftBody: string | undefined = draft.finalBody || draft.proposedBody;
    let sentResult: SendResult | undefined;

    SafeLogger.info(
      `Processing review for draft ${draftId} [Action: ${action}] by ${reviewerName}`
    );

    switch (action) {
      case 'approve': {
        // Approve unedited draft
        email.status = 'approved';
        draft.updatedAt = new Date().toISOString();

        // Update autonomy engine (increments streak)
        await this.autonomyEngine.recordReview(draft.category, 'approve', decisionId);

        if (sendOnApproval) {
          sentResult = await this.emailSender.sendReply({
            email,
            draft,
            isHumanApproved: true,
          });
        }
        break;
      }

      case 'edit': {
        if (!editedBody || editedBody.trim().length === 0) {
          throw new Error('Edited body cannot be empty when choosing the "edit" action.');
        }

        // Apply edits to draft
        draft.finalBody = editedBody.trim();
        finalDraftBody = draft.finalBody;
        draft.updatedAt = new Date().toISOString();
        email.status = 'approved';

        // Update autonomy engine: reset streak to 0!
        await this.autonomyEngine.recordReview(draft.category, 'edit', decisionId);

        if (sendOnApproval) {
          sentResult = await this.emailSender.sendReply({
            email,
            draft,
            isHumanApproved: true,
          });
        }
        break;
      }

      case 'reject': {
        email.status = 'rejected';
        draft.updatedAt = new Date().toISOString();

        // Update autonomy engine: reset streak to 0!
        await this.autonomyEngine.recordReview(draft.category, 'reject', decisionId);
        break;
      }

      case 'escalate': {
        email.status = 'escalated';
        draft.humanReviewRequired = true;
        draft.updatedAt = new Date().toISOString();

        // Update autonomy engine: logs escalation, does not count as approval
        await this.autonomyEngine.recordReview(draft.category, 'escalate', decisionId);
        break;
      }

      case 'regenerate': {
        email.status = 'processing';
        draft.updatedAt = new Date().toISOString();

        // Update autonomy engine: resets streak to 0!
        await this.autonomyEngine.recordReview(draft.category, 'regenerate', decisionId);

        // Regenerate draft if drafter is provided
        if (this.drafter) {
          let kbResponse: KnowledgeBrainResponse;
          if (this.kbClient) {
            try {
              kbResponse = await this.kbClient.query(
                `${email.subject}\n${email.body}`,
                3
              );
            } catch {
              kbResponse = {
                query: email.subject,
                answer: 'Knowledge Brain lookup failed during regeneration.',
                confidence_score: 0.0,
                escalated: true,
                escalation_id: 'regen_kb_error',
                sources: draft.supportingSources || [],
                images: draft.supportingImages || [],
              };
            }
          } else {
            kbResponse = {
              query: email.subject,
              answer: 'Knowledge Brain context retained.',
              confidence_score: 0.9,
              escalated: false,
              sources: draft.supportingSources || [],
              images: draft.supportingImages || [],
            };
          }

          const newDraft = await this.drafter.draftReply(
            email,
            {
              category: draft.category,
              confidence: email.confidence || 0.85,
              extractedQuestion: email.subject,
              reasoning: reviewerFeedback || 'Regenerating based on reviewer request.',
              needsHumanReview: false,
            },
            kbResponse
          );

          // Update current draft with newly generated reply
          draft.proposedBody = newDraft.proposedBody;
          draft.finalBody = undefined;
          draft.supportingSources = newDraft.supportingSources;
          draft.supportingImages = newDraft.supportingImages;
          draft.internalExplanation = `[Regenerated] ${newDraft.internalExplanation}`;
          draft.uncertaintyWarnings = newDraft.uncertaintyWarnings;
          finalDraftBody = newDraft.proposedBody;
        }

        email.status = 'awaiting_review';
        break;
      }

      default:
        throw new Error(`Unsupported review action: ${action}`);
    }

    // Persist audit record of decision
    const decision: ReviewDecision = {
      id: decisionId,
      draftId: draft.id,
      emailId: email.id,
      category: draft.category,
      action,
      previousDraft: previousDraftBody,
      finalDraft: finalDraftBody,
      reviewerFeedback: reviewerFeedback || undefined,
      reviewerName,
      timestamp: new Date().toISOString(),
    };

    this.store.saveEmail(email);
    this.store.saveDraft(draft);
    this.store.addReviewDecision(decision);

    return {
      decision,
      email,
      draft,
      sentResult,
    };
  }

  /**
   * List drafts currently awaiting human review.
   */
  listDraftsAwaitingReview(): DraftReply[] {
    return this.store.listDrafts(true);
  }

  /**
   * Get review decision audit history.
   */
  getReviewHistory(category?: EmailCategory): ReviewDecision[] {
    return this.store.listReviewDecisions(category);
  }
}
