/**
 * Express REST API Application for Task 2: Inbox Agent.
 * Provides endpoints for email intake, human review workflows,
 * draft inspection, autonomy status monitoring, and quality metrics.
 */

import express, { Request, Response, NextFunction } from 'express';
import cors from 'cors';
import path from 'path';
import { InboxAgent } from '../agents/inboxAgent';
import { ReviewService } from '../services/reviewService';
import { ReviewAction } from '../models/types';
import { SafeLogger } from '../utils/logger';
import { SYNTHETIC_EMAILS } from '../data/syntheticEmails';

export function createApp(agent: InboxAgent, reviewService?: ReviewService): express.Application {
  const app = express();
  app.use(cors());
  app.use(express.json({ limit: '10mb' }));

  // Serve Unified Frontend Dashboard
  const publicDir = path.resolve(__dirname, '../../public');
  app.use(express.static(publicDir));

  const activeReviewService =
    reviewService ||
    new ReviewService(
      agent.store,
      agent.autonomyEngine,
      agent.emailSender,
      agent.drafter,
      agent.kbClient
    );

  // Health check
  app.get('/api/v1/inbox/health', (_req: Request, res: Response) => {
    res.json({
      status: 'ok',
      service: 'task2-inbox-agent',
      timestamp: new Date().toISOString(),
      mockLlm: agent.config.mockLlm,
      mockKb: agent.config.mockKb,
      enableRealSending: agent.config.enableRealSending,
    });
  });

  // Synthetic evaluation emails for dashboard demo
  app.get('/api/v1/inbox/synthetic', (_req: Request, res: Response) => {
    res.json({
      success: true,
      count: SYNTHETIC_EMAILS.length,
      emails: SYNTHETIC_EMAILS,
    });
  });

  // 1. Email Intake: Ingest single incoming email
  app.post('/api/v1/inbox/emails', async (req: Request, res: Response, next: NextFunction) => {
    try {
      const { id, senderEmail, senderName, subject, body, metadata } = req.body;
      if (!senderEmail || !subject || body === undefined) {
        res.status(400).json({
          error: 'Validation failed: senderEmail, subject, and body are required fields.',
        });
        return;
      }

      const result = await agent.processEmail({
        id,
        senderEmail,
        senderName,
        subject,
        body,
        metadata,
      });

      res.status(201).json({
        success: true,
        email: result.email,
        draft: result.draft,
        autoSent: result.autoSent,
        sent: result.sent,
      });
    } catch (err) {
      next(err);
    }
  });

  // 2. Batch Email Intake
  app.post('/api/v1/inbox/emails/batch', async (req: Request, res: Response, next: NextFunction) => {
    try {
      const { emails } = req.body;
      if (!Array.isArray(emails)) {
        res.status(400).json({ error: 'Body must contain an "emails" array.' });
        return;
      }

      const results = await agent.batchProcess(emails);
      res.json({
        success: true,
        count: results.length,
        results,
      });
    } catch (err) {
      next(err);
    }
  });

  // 3. List Emails
  app.get('/api/v1/inbox/emails', (_req: Request, res: Response) => {
    const emails = agent.store.listEmails();
    res.json({ success: true, count: emails.length, emails });
  });

  // 4. Get Single Email
  app.get('/api/v1/inbox/emails/:id', (req: Request, res: Response) => {
    const id = req.params.id as string;
    const email = agent.store.getEmail(id);
    if (!email) {
      res.status(404).json({ error: `Email ${id} not found.` });
      return;
    }
    const draft = email.draftId ? agent.store.getDraft(email.draftId) : undefined;
    res.json({ success: true, email, draft });
  });

  // 5. List Drafts
  app.get('/api/v1/inbox/drafts', (req: Request, res: Response) => {
    const awaitingReviewOnly = req.query.awaiting_review === 'true';
    const drafts = agent.store.listDrafts(awaitingReviewOnly);
    res.json({ success: true, count: drafts.length, drafts });
  });

  // 6. Get Single Draft with full context (email & sources)
  app.get('/api/v1/inbox/drafts/:id', (req: Request, res: Response, next: NextFunction) => {
    try {
      const id = req.params.id as string;
      const details = activeReviewService.getReviewItem(id);
      res.json({ success: true, ...details });
    } catch (err) {
      next(err);
    }
  });

  // 7. Human Review: Approve, Edit, Reject, Regenerate, Escalate
  app.post('/api/v1/inbox/drafts/:id/review', async (req: Request, res: Response, next: NextFunction) => {
    try {
      const draftId = req.params.id as string;
      const {
        action,
        editedBody,
        reviewerFeedback,
        reviewerName,
        sendOnApproval,
        decisionId,
      } = req.body;

      const validActions: ReviewAction[] = [
        'approve',
        'edit',
        'reject',
        'regenerate',
        'escalate',
      ];
      if (!action || !validActions.includes(action)) {
        res.status(400).json({
          error: `Invalid review action "${action}". Must be one of: ${validActions.join(', ')}`,
        });
        return;
      }

      const result = await activeReviewService.processReview({
        draftId,
        action,
        editedBody,
        reviewerFeedback,
        reviewerName,
        sendOnApproval: sendOnApproval !== undefined ? sendOnApproval : true,
        decisionId,
      });

      res.json({
        success: true,
        action,
        decision: result.decision,
        email: result.email,
        draft: result.draft,
        sent: result.sentResult,
      });
    } catch (err) {
      next(err);
    }
  });

  // 8. Autonomy Status across all categories
  app.get('/api/v1/inbox/autonomy', (_req: Request, res: Response) => {
    const states = agent.autonomyEngine.getAllStates();
    res.json({
      success: true,
      streakThreshold: agent.config.autonomyStreakThreshold,
      states,
    });
  });

  // 9. Overall Quality & Review Metrics
  app.get('/api/v1/inbox/metrics', (_req: Request, res: Response) => {
    const metrics = agent.autonomyEngine.computeMetrics();
    res.json({
      success: true,
      metrics,
    });
  });

  // 10. Sent Log (Simulated and Live)
  app.get('/api/v1/inbox/sent', (_req: Request, res: Response) => {
    const sent = agent.store.listSent();
    res.json({
      success: true,
      count: sent.length,
      sent,
    });
  });

  // 11. Review Audit Decisions Log
  app.get('/api/v1/inbox/reviews', (req: Request, res: Response) => {
    const category = req.query.category as any;
    const reviews = agent.store.listReviewDecisions(category);
    res.json({
      success: true,
      count: reviews.length,
      reviews,
    });
  });

  // Error handling middleware
  app.use((err: Error, _req: Request, res: Response, _next: NextFunction) => {
    SafeLogger.error('API Error:', err.message);
    const statusCode = err.message.includes('not found')
      ? 404
      : err.message.includes('Validation') || err.message.includes('empty')
      ? 400
      : 500;
    res.status(statusCode).json({
      error: err.message || 'Internal Server Error',
    });
  });

  return app;
}
