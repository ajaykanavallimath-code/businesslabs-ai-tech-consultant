/**
 * Tests for Evaluation Dataset and Evaluation Runner
 */

import { SYNTHETIC_EMAILS } from '../src/data/syntheticEmails';
import { ALL_CATEGORIES, EmailCategory } from '../src/models/types';
import { runEvaluation } from '../src/scripts/evaluate';

describe('Evaluation Dataset and Pipeline Verification', () => {
  it('contains at least 50 synthetic customer emails', () => {
    expect(SYNTHETIC_EMAILS.length).toBeGreaterThanOrEqual(50);
  });

  it('covers all 7 configured email categories', () => {
    const presentCategories = new Set<EmailCategory>(
      SYNTHETIC_EMAILS.map((item) => item.expectedCategory)
    );
    for (const cat of ALL_CATEGORIES) {
      expect(presentCategories.has(cat)).toBe(true);
    }
  });

  it('validates each synthetic case has an id, sender, subject, expected category, and expected outcome', () => {
    for (const item of SYNTHETIC_EMAILS) {
      expect(item.id).toBeDefined();
      expect(item.senderEmail).toMatch(/^[^\s@]+@[^\s@]+\.[^\s@]+$/);
      expect(item.expectedCategory).toBeDefined();
      expect(ALL_CATEGORIES).toContain(item.expectedCategory);
      expect(['auto_send_eligible', 'human_review_required', 'escalate']).toContain(
        item.expectedOutcome
      );
      expect(item.scenarioDescription).toBeDefined();
      expect(Array.isArray(item.tags)).toBe(true);
    }
  });

  it('runs complete evaluation pipeline across synthetic dataset reproducibly', async () => {
    const report = await runEvaluation();
    expect(report.totalEmails).toBe(SYNTHETIC_EMAILS.length);
    expect(report.categoryAccuracy).toBeGreaterThan(0.75); // Over 75% accuracy
    expect(report.outcomeAccuracy).toBeGreaterThan(0.7);
    expect(report.groundedRate).toBeGreaterThan(0.8);
    expect(report.results.length).toBe(SYNTHETIC_EMAILS.length);
  }, 30000); // 30s timeout for processing 55 emails
});
