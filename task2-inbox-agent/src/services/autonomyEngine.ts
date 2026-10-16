/**
 * Strict 20-consecutive-approval autonomy engine with quality-drop withdrawal.
 * Enforces per-category streak tracking, persistent state, and automatic sending gates.
 */

import {
  ALL_CATEGORIES,
  CategoryAutonomyState,
  CategoryMetrics,
  DraftReply,
  EmailCategory,
  OverallMetrics,
  ReviewAction,
} from '../models/types';
import { PersistentStore } from '../storage/persistentStore';
import { AgentConfig, config as globalConfig } from '../utils/config';
import { SafeLogger } from '../utils/logger';

export class AutonomyEngine {
  private store: PersistentStore;
  private config: AgentConfig;
  private processedDecisionIds: Set<string> = new Set();
  private lockPromise: Promise<void> = Promise.resolve();

  constructor(store: PersistentStore, config?: AgentConfig) {
    this.store = store;
    this.config = config || globalConfig;
  }

  /**
   * Acquire a sequential lock to prevent race conditions during concurrent review updates.
   */
  private async withLock<T>(fn: () => Promise<T> | T): Promise<T> {
    let release: () => void;
    const nextLock = new Promise<void>((resolve) => {
      release = resolve;
    });
    const currentLock = this.lockPromise;
    this.lockPromise = (async () => {
      await currentLock;
      await nextLock;
    })();

    try {
      await currentLock;
      return await fn();
    } finally {
      release!();
    }
  }

  /**
   * Record a human review decision and update category autonomy streaks.
   */
  async recordReview(
    category: EmailCategory,
    action: ReviewAction,
    decisionId: string
  ): Promise<CategoryAutonomyState> {
    return this.withLock(() => {
      // Deduplicate: ignore duplicate submissions of the exact same review event
      if (this.processedDecisionIds.has(decisionId)) {
        SafeLogger.warn(`Duplicate review decision ${decisionId} ignored.`);
        return this.store.getAutonomyState(category);
      }
      this.processedDecisionIds.add(decisionId);

      const state = this.store.getAutonomyState(category);
      const now = new Date().toISOString();

      state.totalProcessed += 1;

      // Append to rolling window history
      state.recentHistory.push({ decisionId, action, timestamp: now });
      if (state.recentHistory.length > this.config.qualityWindowSize) {
        state.recentHistory.shift();
      }

      // --- STREAK & AUTONOMY RULE EVALUATION ---
      if (action === 'approve') {
        state.totalApprovedUnedited += 1;
        state.consecutiveUneditedApprovals += 1;

        // Check if the threshold (exactly 20 consecutive approvals) is achieved
        if (
          state.consecutiveUneditedApprovals >= this.config.autonomyStreakThreshold &&
          !state.isAutonomous
        ) {
          state.isAutonomous = true;
          state.autonomyGrantedAt = now;
          state.autonomyWithdrawnAt = null;
          state.autonomyWithdrawalReason = null;
          SafeLogger.info(
            `[AUTONOMY GRANTED] Category "${category}" reached ${this.config.autonomyStreakThreshold} consecutive unedited approvals.`
          );
        }
      } else if (action === 'edit') {
        state.totalEdited += 1;
        state.consecutiveUneditedApprovals = 0; // Strict reset of consecutive streak
      } else if (action === 'reject' || action === 'regenerate') {
        state.totalRejected += 1;
        state.consecutiveUneditedApprovals = 0; // Strict reset of consecutive streak
      } else if (action === 'escalate') {
        state.totalEscalated += 1;
        // Escalations are routed to human experts; streak is not incremented
      }

      // --- QUALITY-BASED ROLLING WITHDRAWAL CHECK ---
      if (state.isAutonomous) {
        this.checkQualityDecline(state, now);
      }

      this.store.updateAutonomyState(state);
      return state;
    });
  }

  /**
   * Evaluates rolling window quality and revokes autonomy if edit/rejection rate exceeds threshold.
   */
  private checkQualityDecline(state: CategoryAutonomyState, timestamp: string): void {
    const windowCount = state.recentHistory.length;
    if (windowCount === 0) return;

    const edits = state.recentHistory.filter((h) => h.action === 'edit').length;
    const rejections = state.recentHistory.filter(
      (h) => h.action === 'reject' || h.action === 'regenerate'
    ).length;

    const editRate = edits / windowCount;
    const rejectionRate = rejections / windowCount;

    if (
      editRate > this.config.qualityMaxEditRate ||
      rejectionRate > this.config.qualityMaxRejectionRate
    ) {
      this.withdrawAutonomy(
        state,
        `Quality decline detected in rolling window of ${windowCount} reviews (Edit Rate: ${(editRate * 100).toFixed(1)}%, Rejection Rate: ${(rejectionRate * 100).toFixed(1)}%). Threshold exceeded.`,
        timestamp
      );
    }
  }

  private withdrawAutonomy(
    state: CategoryAutonomyState,
    reason: string,
    timestamp: string
  ): void {
    state.isAutonomous = false;
    state.consecutiveUneditedApprovals = 0;
    state.autonomyWithdrawnAt = timestamp;
    state.autonomyWithdrawalReason = reason;
    SafeLogger.warn(`[AUTONOMY WITHDRAWN] Category "${state.category}": ${reason}`);
  }

  /**
   * Verifies whether an email draft is eligible for automatic sending.
   * Enforces that even in an autonomous category, uncertain drafts cannot be auto-sent.
   */
  canAutoSend(
    category: EmailCategory,
    draft?: DraftReply
  ): { allowed: boolean; reason: string } {
    const state = this.store.getAutonomyState(category);

    if (!state.isAutonomous) {
      return {
        allowed: false,
        reason: `Category "${category}" has not reached ${this.config.autonomyStreakThreshold} consecutive unedited approvals (Current streak: ${state.consecutiveUneditedApprovals}).`,
      };
    }

    if (state.autonomyWithdrawnAt) {
      return {
        allowed: false,
        reason: `Autonomy was withdrawn for category "${category}": ${state.autonomyWithdrawalReason}. Requires 20 new consecutive approvals to recover.`,
      };
    }

    if (!draft) {
      return { allowed: true, reason: 'Category is autonomous.' };
    }

    // Safety checks on the specific draft
    if (draft.humanReviewRequired) {
      return {
        allowed: false,
        reason: 'Draft requires human review due to ambiguity, sensitivity, or missing information.',
      };
    }

    if (!draft.supportingSources || draft.supportingSources.length === 0) {
      return {
        allowed: false,
        reason: 'Draft has no supporting Knowledge Brain citations; unverified claims cannot be sent autonomously.',
      };
    }

    return {
      allowed: true,
      reason: `Category "${category}" is autonomous and draft satisfies all factual grounding criteria.`,
    };
  }

  /**
   * Calculate metrics for a single category.
   */
  getCategoryMetrics(category: EmailCategory): CategoryMetrics {
    const state = this.store.getAutonomyState(category);
    const total = state.totalProcessed;

    const approvalRate = total > 0 ? state.totalApprovedUnedited / total : 0;
    const editRate = total > 0 ? state.totalEdited / total : 0;
    const rejectionRate = total > 0 ? state.totalRejected / total : 0;
    const escalationRate = total > 0 ? state.totalEscalated / total : 0;

    const recentCount = state.recentHistory.length;
    const recentEditsOrRejects = state.recentHistory.filter(
      (h) => h.action === 'edit' || h.action === 'reject' || h.action === 'regenerate'
    ).length;
    const recentEditOrRejectionRate = recentCount > 0 ? recentEditsOrRejects / recentCount : 0;

    return {
      category,
      consecutiveUneditedApprovals: state.consecutiveUneditedApprovals,
      isAutonomous: state.isAutonomous,
      totalProcessed: total,
      approvalRate: Number(approvalRate.toFixed(4)),
      editRate: Number(editRate.toFixed(4)),
      rejectionRate: Number(rejectionRate.toFixed(4)),
      escalationRate: Number(escalationRate.toFixed(4)),
      recentEditOrRejectionRate: Number(recentEditOrRejectionRate.toFixed(4)),
      withdrawalReason: state.autonomyWithdrawalReason,
    };
  }

  /**
   * Calculate overall metrics across all email categories.
   */
  getOverallMetrics(): OverallMetrics {
    const emails = this.store.listEmails();
    const drafts = this.store.listDrafts();
    const sent = this.store.listSent();

    const categories = {} as Record<EmailCategory, CategoryMetrics>;
    for (const cat of ALL_CATEGORIES) {
      categories[cat] = this.getCategoryMetrics(cat);
    }

    return {
      totalEmails: emails.length,
      totalDrafts: drafts.length,
      totalSent: sent.length,
      totalAwaitingReview: emails.filter((e) => e.status === 'awaiting_review').length,
      totalEscalated: emails.filter((e) => e.status === 'escalated').length,
      categories,
    };
  }

  getCategoryState(category: EmailCategory): CategoryAutonomyState {
    return this.store.getAutonomyState(category);
  }

  getAllStates(): Record<EmailCategory, CategoryAutonomyState> {
    return this.store.getAllAutonomyStates();
  }

  computeMetrics(): OverallMetrics {
    return this.getOverallMetrics();
  }
}
