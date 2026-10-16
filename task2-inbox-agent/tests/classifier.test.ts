/**
 * Tests for Email Intake and Categorization
 */

import { EmailClassifier } from '../src/services/classifier';
import { CustomerEmail } from '../src/models/types';
import { AgentConfig, loadConfig } from '../src/utils/config';

describe('EmailClassifier', () => {
  let classifier: EmailClassifier;
  let testConfig: AgentConfig;

  beforeEach(() => {
    testConfig = loadConfig({
      port: 3001,
      mockLlm: true,
      mockKb: true,
      logLevel: 'error',
    });
    classifier = new EmailClassifier(testConfig);
  });

  it('classifies technical support email correctly', async () => {
    const email: CustomerEmail = {
      id: 'e1',
      senderEmail: 'test@example.com',
      subject: 'SSL Certificate error on custom domain',
      body: 'Hi, our SSL certificate is failing to generate and visitors get a 500 or security warning on DNS.',
      receivedAt: new Date().toISOString(),
      status: 'received',
    };

    const result = await classifier.classify(email);
    expect(result.category).toBe('technical_support');
    expect(result.confidence).toBeGreaterThan(0.7);
    expect(result.needsHumanReview).toBe(false);
  });

  it('classifies billing and payment inquiries correctly', async () => {
    const email: CustomerEmail = {
      id: 'e2',
      senderEmail: 'billing@client.com',
      subject: 'Invoice receipt and Stripe credit card charge',
      body: 'Can you please send me the VAT receipt for our annual subscription payment and refund duplicate charges?',
      receivedAt: new Date().toISOString(),
      status: 'received',
    };

    const result = await classifier.classify(email);
    expect(result.category).toBe('billing_and_payments');
    expect(result.confidence).toBeGreaterThan(0.7);
  });

  it('classifies account and login issues correctly', async () => {
    const email: CustomerEmail = {
      id: 'e3',
      senderEmail: 'user@client.com',
      subject: 'Forgot password reset link expired',
      body: 'I am locked out of my account and my 2FA authentication code is not working.',
      receivedAt: new Date().toISOString(),
      status: 'received',
    };

    const result = await classifier.classify(email);
    expect(result.category).toBe('account_and_login');
  });

  it('classifies product configuration and how-to questions correctly', async () => {
    const email: CustomerEmail = {
      id: 'e4',
      senderEmail: 'admin@portal.com',
      subject: 'How to add dropdown fields in form manager',
      body: 'Where do I edit the member signup form fields and customize the navigation menu?',
      receivedAt: new Date().toISOString(),
      status: 'received',
    };

    const result = await classifier.classify(email);
    expect(result.category).toBe('product_configuration');
  });

  it('classifies feature requests correctly', async () => {
    const email: CustomerEmail = {
      id: 'e5',
      senderEmail: 'user@fan.org',
      subject: 'Feature request: native iOS and Android mobile app',
      body: 'We would love if you could add crypto payments or a mobile app to your roadmap!',
      receivedAt: new Date().toISOString(),
      status: 'received',
    };

    const result = await classifier.classify(email);
    expect(result.category).toBe('feature_request');
  });

  it('classifies complaints and angry feedback correctly', async () => {
    const email: CustomerEmail = {
      id: 'e6',
      senderEmail: 'angry@buyer.com',
      subject: 'Extremely disappointed: site downtime broke our sales',
      body: 'This service is completely unacceptable. Terrible experience and awful support delay!',
      receivedAt: new Date().toISOString(),
      status: 'received',
    };

    const result = await classifier.classify(email);
    expect(result.category).toBe('complaints');
  });

  it('flags vague, empty, or ambiguous inquiries as other_or_uncertain and routes to human review', async () => {
    const email: CustomerEmail = {
      id: 'e7',
      senderEmail: 'vague@domain.com',
      subject: 'Help',
      body: 'It stopped.',
      receivedAt: new Date().toISOString(),
      status: 'received',
    };

    const result = await classifier.classify(email);
    expect(result.category).toBe('other_or_uncertain');
    expect(result.needsHumanReview).toBe(true);
    expect(result.uncertaintyReason).toBeDefined();
  });

  it('handles empty body gracefully without throwing', async () => {
    const email: CustomerEmail = {
      id: 'e8',
      senderEmail: 'empty@domain.com',
      subject: '',
      body: '',
      receivedAt: new Date().toISOString(),
      status: 'received',
    };

    const result = await classifier.classify(email);
    expect(result.category).toBe('other_or_uncertain');
    expect(result.needsHumanReview).toBe(true);
  });
});
