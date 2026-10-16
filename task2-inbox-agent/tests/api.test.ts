/**
 * Integration Tests for Task 2 REST API (Supertest)
 */

import * as fs from 'fs';
import * as path from 'path';
import request from 'supertest';
import { createApp } from '../src/api/app';
import { InboxAgent } from '../src/agents/inboxAgent';
import { PersistentStore } from '../src/storage/persistentStore';
import { AgentConfig, loadConfig } from '../src/utils/config';

describe('Task 2 REST API Endpoints', () => {
  const testDataDir = path.resolve(__dirname, '../data/test_api');
  let app: any;
  let agent: InboxAgent;
  let store: PersistentStore;
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
    agent = new InboxAgent({ store, config: testConfig });
    app = createApp(agent);
  });

  afterAll(() => {
    if (fs.existsSync(testDataDir)) {
      fs.rmSync(testDataDir, { recursive: true, force: true });
    }
  });

  it('GET /api/v1/inbox/health returns status ok', async () => {
    const res = await request(app).get('/api/v1/inbox/health');
    expect(res.status).toBe(200);
    expect(res.body.status).toBe('ok');
    expect(res.body.service).toBe('task2-inbox-agent');
  });

  it('POST /api/v1/inbox/emails ingests customer email and generates draft reply', async () => {
    const payload = {
      senderEmail: 'alex@startup.org',
      senderName: 'Alex Rivera',
      subject: 'How do I add custom dropdown fields to member form?',
      body: 'Hi Support, which menu in the admin dashboard allows me to add dropdown choices to registration?',
    };

    const res = await request(app).post('/api/v1/inbox/emails').send(payload);
    expect(res.status).toBe(201);
    expect(res.body.success).toBe(true);
    expect(res.body.email.id).toBeDefined();
    expect(res.body.email.category).toBe('product_configuration');
    expect(res.body.draft.id).toBeDefined();
    expect(res.body.draft.proposedBody).toContain('Hello Alex Rivera,');
    expect(res.body.draft.supportingSources.length).toBeGreaterThan(0);
  });

  it('POST /api/v1/inbox/emails rejects invalid requests missing required fields', async () => {
    const res = await request(app)
      .post('/api/v1/inbox/emails')
      .send({ senderEmail: 'missing_subject@domain.com' });
    expect(res.status).toBe(400);
    expect(res.body.error).toContain('Validation failed');
  });

  it('GET /api/v1/inbox/drafts and GET /api/v1/inbox/drafts/:id return draft details', async () => {
    // 1. Ingest email
    const emailRes = await request(app).post('/api/v1/inbox/emails').send({
      senderEmail: 'test@example.com',
      subject: 'SSL Certificate error',
      body: 'SSL is not generating for custom domain.',
    });
    const draftId = emailRes.body.draft.id;

    // 2. List drafts
    const listRes = await request(app).get('/api/v1/inbox/drafts');
    expect(listRes.status).toBe(200);
    expect(listRes.body.drafts.length).toBe(1);

    // 3. Get single draft
    const singleRes = await request(app).get(`/api/v1/inbox/drafts/${draftId}`);
    expect(singleRes.status).toBe(200);
    expect(singleRes.body.draft.id).toBe(draftId);
    expect(singleRes.body.email.subject).toContain('SSL Certificate error');
    expect(singleRes.body.sources).toBeDefined();
  });

  it('POST /api/v1/inbox/drafts/:id/review executes human review action and updates autonomy', async () => {
    // 1. Ingest email
    const emailRes = await request(app).post('/api/v1/inbox/emails').send({
      senderEmail: 'test@example.com',
      subject: 'SSL Certificate error',
      body: 'Need help with SSL certificate error and nameservers.',
    });
    const draftId = emailRes.body.draft.id;

    // 2. Review: approve
    const reviewRes = await request(app)
      .post(`/api/v1/inbox/drafts/${draftId}/review`)
      .send({
        action: 'approve',
        reviewerName: 'Lead Reviewer',
        sendOnApproval: true,
      });

    expect(reviewRes.status).toBe(200);
    expect(reviewRes.body.success).toBe(true);
    expect(reviewRes.body.action).toBe('approve');
    expect(reviewRes.body.email.status).toBe('sent');
    expect(reviewRes.body.sent.simulated).toBe(true);

    // 3. Check autonomy status
    const autoRes = await request(app).get('/api/v1/inbox/autonomy');
    expect(autoRes.status).toBe(200);
    expect(autoRes.body.states.technical_support.consecutiveUneditedApprovals).toBe(1);

    // 4. Check metrics
    const metricsRes = await request(app).get('/api/v1/inbox/metrics');
    expect(metricsRes.status).toBe(200);
    expect(metricsRes.body.metrics.totalSent).toBe(1);
  });

  it('GET /api/v1/inbox/sent lists sent records', async () => {
    const res = await request(app).get('/api/v1/inbox/sent');
    expect(res.status).toBe(200);
    expect(Array.isArray(res.body.sent)).toBe(true);
  });

  it('GET /api/v1/inbox/synthetic returns all 55 synthetic customer emails', async () => {
    const res = await request(app).get('/api/v1/inbox/synthetic');
    expect(res.status).toBe(200);
    expect(res.body.success).toBe(true);
    expect(res.body.count).toBe(55);
    expect(res.body.emails.length).toBe(55);
  });

  it('GET / serves the static unified frontend dashboard HTML', async () => {
    const res = await request(app).get('/');
    expect(res.status).toBe(200);
    expect(res.text).toContain('BusinessLabs');
    expect(res.text).toContain('AI Tech Consultant');
  });
});
