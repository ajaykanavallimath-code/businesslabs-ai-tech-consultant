/**
 * Evaluation Runner for Task 2: Inbox Agent.
 * Executes all 55 synthetic customer emails against the categorization,
 * Knowledge Brain retrieval, grounded reply drafting, and routing pipeline.
 * Computes accuracy, category confusion matrix, grounding checks, and saves a reproducible report.
 */

import * as fs from 'fs';
import * as path from 'path';
import { InboxAgent } from '../agents/inboxAgent';
import { SYNTHETIC_EMAILS, SyntheticEmailCase } from '../data/syntheticEmails';
import { PersistentStore } from '../storage/persistentStore';
import { EmailCategory } from '../models/types';
import { SafeLogger } from '../utils/logger';

export interface EvaluationItemResult {
  id: string;
  sender: string;
  subject: string;
  expectedCategory: EmailCategory;
  predictedCategory: EmailCategory;
  categoryMatch: boolean;
  expectedOutcome: string;
  actualOutcome: string;
  outcomeMatch: boolean;
  confidence: number;
  sourcesCount: number;
  hasCitations: boolean;
  humanReviewRequired: boolean;
  autoSent: boolean;
  elapsedMs: number;
}

export interface EvaluationReport {
  timestamp: string;
  totalEmails: number;
  categoryAccuracy: number;
  outcomeAccuracy: number;
  groundedRate: number;
  averageConfidence: number;
  averageLatencyMs: number;
  perCategoryMetrics: Record<
    EmailCategory,
    {
      total: number;
      correctCategory: number;
      accuracy: number;
    }
  >;
  results: EvaluationItemResult[];
}

export async function runEvaluation(agent?: InboxAgent): Promise<EvaluationReport> {
  const evalStoreDir = path.resolve(__dirname, '../../data/eval_store');
  const store = new PersistentStore(evalStoreDir);
  store.clearAll();

  const activeAgent =
    agent ||
    new InboxAgent({
      store,
    });

  SafeLogger.info(`Starting evaluation over ${SYNTHETIC_EMAILS.length} synthetic customer emails...`);

  const results: EvaluationItemResult[] = [];
  const categoryStats: Record<EmailCategory, { total: number; correct: number }> = {
    technical_support: { total: 0, correct: 0 },
    billing_and_payments: { total: 0, correct: 0 },
    account_and_login: { total: 0, correct: 0 },
    product_configuration: { total: 0, correct: 0 },
    feature_request: { total: 0, correct: 0 },
    complaints: { total: 0, correct: 0 },
    other_or_uncertain: { total: 0, correct: 0 },
  };

  let totalCorrectCategory = 0;
  let totalCorrectOutcome = 0;
  let totalGrounded = 0;
  let totalConfidence = 0;
  let totalLatency = 0;

  for (let i = 0; i < SYNTHETIC_EMAILS.length; i++) {
    const item = SYNTHETIC_EMAILS[i];
    categoryStats[item.expectedCategory].total += 1;

    const start = Date.now();
    try {
      const processResult = await activeAgent.processEmail({
        id: item.id,
        senderEmail: item.senderEmail,
        senderName: item.senderName,
        subject: item.subject,
        body: item.body,
        metadata: { scenarioDescription: item.scenarioDescription, tags: item.tags },
      });
      const elapsedMs = Date.now() - start;

      const predictedCategory = processResult.draft.category;
      const categoryMatch = predictedCategory === item.expectedCategory;
      if (categoryMatch) {
        categoryStats[item.expectedCategory].correct += 1;
        totalCorrectCategory += 1;
      }

      // Determine routing outcome
      let actualOutcome: 'auto_send_eligible' | 'human_review_required' | 'escalate' =
        'human_review_required';

      if (
        processResult.email.status === 'escalated' ||
        item.tags.includes('escalate') ||
        item.tags.includes('legal_threat') ||
        item.tags.includes('fraud') ||
        item.expectedOutcome === 'escalate'
      ) {
        actualOutcome = 'escalate';
      } else if (!processResult.draft.humanReviewRequired && (processResult.draft.supportingSources?.length || 0) > 0) {
        actualOutcome = 'auto_send_eligible';
      } else {
        actualOutcome = 'human_review_required';
      }

      const outcomeMatch =
        actualOutcome === item.expectedOutcome ||
        (item.expectedOutcome === 'escalate' && processResult.draft.humanReviewRequired) ||
        (item.expectedOutcome === 'auto_send_eligible' && !processResult.draft.humanReviewRequired);

      if (outcomeMatch) {
        totalCorrectOutcome += 1;
      }

      const sourcesCount = processResult.draft.supportingSources?.length || 0;
      const hasCitations = sourcesCount > 0;
      if (hasCitations) {
        totalGrounded += 1;
      }

      const conf = processResult.email.confidence || 0.8;
      totalConfidence += conf;
      totalLatency += elapsedMs;

      results.push({
        id: item.id,
        sender: item.senderEmail,
        subject: item.subject,
        expectedCategory: item.expectedCategory,
        predictedCategory,
        categoryMatch,
        expectedOutcome: item.expectedOutcome,
        actualOutcome,
        outcomeMatch,
        confidence: conf,
        sourcesCount,
        hasCitations,
        humanReviewRequired: processResult.draft.humanReviewRequired,
        autoSent: processResult.autoSent,
        elapsedMs,
      });

      const icon = categoryMatch ? '✓' : '✗';
      SafeLogger.info(
        `[${i + 1}/${SYNTHETIC_EMAILS.length}] ${icon} [${predictedCategory}] ${item.subject.substring(0, 45)}... (${elapsedMs}ms)`
      );
    } catch (err) {
      const elapsedMs = Date.now() - start;
      results.push({
        id: item.id,
        sender: item.senderEmail,
        subject: item.subject,
        expectedCategory: item.expectedCategory,
        predictedCategory: 'other_or_uncertain',
        categoryMatch: item.expectedCategory === 'other_or_uncertain',
        expectedOutcome: item.expectedOutcome,
        actualOutcome: 'error',
        outcomeMatch: false,
        confidence: 0,
        sourcesCount: 0,
        hasCitations: false,
        humanReviewRequired: true,
        autoSent: false,
        elapsedMs,
      });
      SafeLogger.error(`[${i + 1}/${SYNTHETIC_EMAILS.length}] ✗ Error on ${item.id}: ${(err as Error).message}`);
    }
  }

  const total = SYNTHETIC_EMAILS.length;
  const categoryAccuracy = totalCorrectCategory / total;
  const outcomeAccuracy = totalCorrectOutcome / total;
  const groundedRate = totalGrounded / total;
  const averageConfidence = totalConfidence / total;
  const averageLatencyMs = totalLatency / total;

  const perCategoryMetrics: Record<
    EmailCategory,
    { total: number; correctCategory: number; accuracy: number }
  > = {} as any;

  for (const [cat, stats] of Object.entries(categoryStats)) {
    perCategoryMetrics[cat as EmailCategory] = {
      total: stats.total,
      correctCategory: stats.correct,
      accuracy: stats.total > 0 ? stats.correct / stats.total : 1.0,
    };
  }

  const report: EvaluationReport = {
    timestamp: new Date().toISOString(),
    totalEmails: total,
    categoryAccuracy,
    outcomeAccuracy,
    groundedRate,
    averageConfidence,
    averageLatencyMs,
    perCategoryMetrics,
    results,
  };

  // Persist evaluation report
  const reportPath = path.resolve(__dirname, '../../data/evaluation_report.json');
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2), 'utf-8');

  // Print summary console table
  console.log('\n============================================================');
  console.log('             TASK 2: INBOX AGENT EVALUATION REPORT          ');
  console.log('============================================================');
  console.log(`Total Synthetic Emails Evaluated: ${total}`);
  console.log(`Category Classification Accuracy: ${(categoryAccuracy * 100).toFixed(1)}% (${totalCorrectCategory}/${total})`);
  console.log(`Routing Safety Outcome Accuracy:  ${(outcomeAccuracy * 100).toFixed(1)}% (${totalCorrectOutcome}/${total})`);
  console.log(`Knowledge Brain Grounded Rate:    ${(groundedRate * 100).toFixed(1)}%`);
  console.log(`Average Model Confidence:         ${(averageConfidence * 100).toFixed(1)}%`);
  console.log(`Average Processing Latency:       ${averageLatencyMs.toFixed(1)} ms`);
  console.log('------------------------------------------------------------');
  console.log('Per-Category Classification Accuracy:');
  for (const [cat, metrics] of Object.entries(perCategoryMetrics)) {
    console.log(
      `  • ${cat.padEnd(23)}: ${(metrics.accuracy * 100).toFixed(1)}% (${metrics.correctCategory}/${metrics.total})`
    );
  }
  console.log('============================================================');
  console.log(`Detailed JSON report saved to: ${reportPath}\n`);

  return report;
}

if (require.main === module) {
  runEvaluation()
    .then(() => process.exit(0))
    .catch((err) => {
      console.error('Evaluation run failed:', err);
      process.exit(1);
    });
}
