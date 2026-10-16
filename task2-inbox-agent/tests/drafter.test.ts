/**
 * Tests for Grounded Reply Drafter
 */

import { ReplyDrafter } from '../src/services/drafter';
import { CustomerEmail, KnowledgeBrainResponse } from '../src/models/types';
import { ClassificationResult } from '../src/services/classifier';
import { AgentConfig, loadConfig } from '../src/utils/config';

describe('ReplyDrafter', () => {
  let drafter: ReplyDrafter;
  let testConfig: AgentConfig;

  beforeEach(() => {
    testConfig = loadConfig({
      port: 3001,
      mockLlm: true,
      mockKb: true,
      logLevel: 'error',
    });
    drafter = new ReplyDrafter(testConfig);
  });

  it('generates a polite, evidence-grounded draft with citations and screenshots', async () => {
    const email: CustomerEmail = {
      id: 'e1',
      senderEmail: 'marcus@example.org',
      senderName: 'Marcus',
      subject: 'Custom domain setup instructions',
      body: 'How do I point my domain nameservers to Brilliant Directories?',
      receivedAt: new Date().toISOString(),
      status: 'received',
      category: 'technical_support',
    };

    const classification: ClassificationResult = {
      category: 'technical_support',
      confidence: 0.95,
      extractedQuestion: 'How to point custom domain nameservers?',
      reasoning: 'Domain and DNS question',
      needsHumanReview: false,
    };

    const kbResponse: KnowledgeBrainResponse = {
      query: email.subject,
      answer: 'Update your domain nameservers at your domain registrar.',
      confidence_score: 0.92,
      escalated: false,
      sources: [
        {
          title: 'How to Point Your Custom Domain via DNS Nameservers',
          url: 'https://support.brilliantdirectories.com/support/solutions/articles/how-to-point-domain',
          snippet: 'Log into your domain registrar and set nameservers to ns1.bd.com and ns2.bd.com.',
          score: 0.95,
        },
      ],
      images: [
        {
          url: 'https://support.brilliantdirectories.com/images/dns_setup.png',
          caption: 'Domain Manager DNS Settings Screen',
        },
      ],
    };

    const draft = await drafter.draftReply(email, classification, kbResponse);

    expect(draft.id).toBeDefined();
    expect(draft.proposedBody).toContain('Hello Marcus,');
    expect(draft.proposedBody).toContain('Brilliant Directories Technical Support');
    expect(draft.proposedBody).toContain(kbResponse.sources[0].url);
    expect(draft.proposedBody).toContain(kbResponse.images[0].url);
    expect(draft.supportingSources.length).toBe(1);
    expect(draft.humanReviewRequired).toBe(false);
  });

  it('routes draft to human review when Knowledge Brain flags escalation or low confidence', async () => {
    const email: CustomerEmail = {
      id: 'e2',
      senderEmail: 'user@example.com',
      subject: 'Unsupported custom feature',
      body: 'Can I rewrite PHP core code?',
      receivedAt: new Date().toISOString(),
      status: 'received',
    };

    const classification: ClassificationResult = {
      category: 'other_or_uncertain',
      confidence: 0.5,
      extractedQuestion: 'Can I rewrite PHP core code?',
      reasoning: 'Unsupported capability',
      needsHumanReview: true,
    };

    const kbResponse: KnowledgeBrainResponse = {
      query: email.subject,
      answer: 'No documentation available for core PHP modifications.',
      confidence_score: 0.35,
      escalated: true,
      escalation_id: 'esc_123',
      sources: [],
      images: [],
    };

    const draft = await drafter.draftReply(email, classification, kbResponse);

    expect(draft.humanReviewRequired).toBe(true);
    expect(draft.uncertaintyWarnings.length).toBeGreaterThan(0);
  });
});
