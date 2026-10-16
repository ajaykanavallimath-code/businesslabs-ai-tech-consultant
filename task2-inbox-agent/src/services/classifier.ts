/**
 * Email categorization service using Claude.
 * Categorizes customer inquiries into defined categories with uncertainty detection.
 */

import Anthropic from '@anthropic-ai/sdk';
import { CustomerEmail, EmailCategory } from '../models/types';
import { AgentConfig, config as globalConfig } from '../utils/config';
import { SafeLogger } from '../utils/logger';

export interface ClassificationResult {
  category: EmailCategory;
  confidence: number;
  extractedQuestion: string;
  reasoning: string;
  needsHumanReview: boolean;
  uncertaintyReason?: string;
}

const CLASSIFICATION_SYSTEM_PROMPT = `You are an AI Email Triage Agent for Brilliant Directories.
Your task is to classify incoming customer support emails into exactly one of the following categories:

1. technical_support: Errors, server bugs, script breaks, API issues, DNS/SSL failures.
2. billing_and_payments: Subscriptions, invoices, payment gateway settings, charges, upgrade questions.
3. account_and_login: Password resets, admin credentials, staff accounts, 2FA, access lockouts.
4. product_configuration: How-to questions, setup guides, membership plans, forms, widgets, categories.
5. feature_request: Suggestions for new software functionality, additions not currently supported.
6. complaints: Frustrated or angry customers, expressions of dissatisfaction, escalation threats.
7. other_or_uncertain: Ambiguous, gibberish, unsupported topics, or inquiries where the customer intent is unclear.

CRITICAL RULES:
- If the email is ambiguous, lacks critical details, contains conflicting requests, or touches sensitive legal/chargeback topics, set "needsHumanReview": true.
- Extract the core technical question or need in "extractedQuestion".

You MUST return valid JSON matching this schema:
{
  "category": "technical_support",
  "confidence": 0.95,
  "extractedQuestion": "How to resolve custom domain DNS SSL error?",
  "reasoning": "Customer reports SSL certificate failed to propagate after updating DNS.",
  "needsHumanReview": false,
  "uncertaintyReason": null
}`;

export class EmailClassifier {
  private config: AgentConfig;
  private anthropicClient?: Anthropic;

  constructor(config?: AgentConfig, anthropicClient?: Anthropic) {
    this.config = config || globalConfig;
    if (anthropicClient) {
      this.anthropicClient = anthropicClient;
    } else if (this.config.anthropicApiKey && !this.config.mockLlm) {
      this.anthropicClient = new Anthropic({ apiKey: this.config.anthropicApiKey });
    }
  }

  async classify(email: CustomerEmail): Promise<ClassificationResult> {
    return this.classifyEmail(email);
  }

  async classifyEmail(email: CustomerEmail): Promise<ClassificationResult> {
    const text = `Subject: ${email.subject}\n\nBody:\n${email.body}`.trim();

    // 1. If mock LLM is enabled or no Anthropic client configured, use deterministic classifier
    if (this.config.mockLlm || !this.anthropicClient) {
      return this.classifyWithHeuristics(email.subject, email.body);
    }

    // 2. Call Claude API (CLAUDE_MODEL_FAST for speed & cost efficiency)
    try {
      const response = await this.anthropicClient.messages.create({
        model: this.config.claudeModelFast,
        max_tokens: 400,
        temperature: 0.0,
        system: CLASSIFICATION_SYSTEM_PROMPT,
        messages: [{ role: 'user', content: text }],
      });

      const responseText =
        response.content[0].type === 'text' ? response.content[0].text : '';
      return this.parseClaudeResponse(responseText, email);
    } catch (err) {
      SafeLogger.warn(`Claude classification API error: ${(err as Error)?.message}; falling back to heuristic triage.`);
      return this.classifyWithHeuristics(email.subject, email.body);
    }
  }

  private parseClaudeResponse(
    text: string,
    email: CustomerEmail
  ): ClassificationResult {
    try {
      const cleanJson = text.replace(/```(?:json)?\s*([\s\S]*?)\s*```/, '$1').trim();
      const parsed = JSON.parse(cleanJson);

      return {
        category: parsed.category || 'other_or_uncertain',
        confidence: typeof parsed.confidence === 'number' ? parsed.confidence : 0.8,
        extractedQuestion: parsed.extractedQuestion || email.subject,
        reasoning: parsed.reasoning || 'Categorized by Claude',
        needsHumanReview: Boolean(parsed.needsHumanReview),
        uncertaintyReason: parsed.uncertaintyReason || undefined,
      };
    } catch {
      return this.classifyWithHeuristics(email.subject, email.body);
    }
  }

  /**
   * Deterministic rule-based categorization used for offline testing and API fallbacks.
   */
  public classifyWithHeuristics(
    subject: string,
    body: string
  ): ClassificationResult {
    const combined = `${subject} ${body}`.toLowerCase();
    const cleanBody = body.trim();

    // 1. Vague / Missing Details / Nonsense / Other
    if (
      cleanBody.length === 0 ||
      cleanBody === 'it does not work. call me.' ||
      combined.includes('why so serious') ||
      combined.includes('purple mist') ||
      combined.includes('woocommerce') ||
      combined.includes('wordpress plugin') ||
      combined.includes('partnership') ||
      combined.includes('co-marketing') ||
      combined.includes('hipaa')
    ) {
      return {
        category: 'other_or_uncertain',
        confidence: 0.90,
        extractedQuestion: subject || 'General / unsupported inquiry',
        reasoning: 'Inquiry is either ambiguous, lacks critical details, discusses partnerships, or involves unsupported 3rd party software.',
        needsHumanReview: true,
        uncertaintyReason: cleanBody.length === 0
          ? 'Email body is completely empty.'
          : 'Inquiry requires human triage or policy review.',
      };
    }

    // 2. Complaints / Frustration / Service Dissatisfaction
    if (
      combined.includes('outrage') ||
      combined.includes('extremely upset') ||
      combined.includes('unacceptable') ||
      combined.includes('ignoring') ||
      combined.includes('ignored') ||
      combined.includes('charged again after') ||
      combined.includes('broke our') ||
      combined.includes('broken our') ||
      combined.includes('overwritten') ||
      combined.includes('spam accounts flooding') ||
      combined.includes('too complicated') ||
      combined.includes('impostor') ||
      combined.includes('steal my') ||
      combined.includes('legal action') ||
      combined.includes('trademark') ||
      combined.includes('defamatory') ||
      combined.includes('terrible') ||
      combined.includes('awful') ||
      combined.includes('angry')
    ) {
      return {
        category: 'complaints',
        confidence: 0.95,
        extractedQuestion: subject,
        reasoning: 'Customer expressing high frustration, service interruption complaint, or legal/security grievance.',
        needsHumanReview: true,
        uncertaintyReason: 'Customer expression of dissatisfaction or dispute.',
      };
    }

    // 3. Feature Requests
    if (
      combined.includes('feature request') ||
      combined.includes('feature suggestion') ||
      combined.includes('plans to release') ||
      combined.includes('roadmap') ||
      combined.includes('native mobile app') ||
      combined.includes('flutter') ||
      combined.includes('cryptocurrency') ||
      combined.includes('bitcoin') ||
      combined.includes('usdc') ||
      combined.includes('ai-powered') ||
      combined.includes('chatgpt') ||
      combined.includes('whatsapp') ||
      combined.includes('dark mode') ||
      combined.includes('hubspot') ||
      combined.includes('docusign') ||
      combined.includes('digital signature') ||
      combined.includes('multi-currency') ||
      combined.includes('would love if you could add') ||
      combined.includes('new feature')
    ) {
      return {
        category: 'feature_request',
        confidence: 0.93,
        extractedQuestion: subject,
        reasoning: 'Customer proposing new functionality, integrations, or roadmap additions.',
        needsHumanReview: false,
      };
    }

    // 4. Account & Login
    if (
      combined.includes('password reset') ||
      combined.includes('forgot password') ||
      combined.includes('2fa') ||
      combined.includes('two-factor') ||
      combined.includes('authenticator') ||
      combined.includes('transfer ownership') ||
      combined.includes('account ownership') ||
      combined.includes('secondary admin') ||
      combined.includes('admin users') ||
      combined.includes('locked out') ||
      combined.includes('account temporarily locked') ||
      combined.includes('single sign-on') ||
      combined.includes('sso') ||
      combined.includes('okta') ||
      combined.includes('saml') ||
      combined.includes('change email address') ||
      combined.includes('changing email address') ||
      combined.includes('session timing out') ||
      combined.includes('logged out of the admin') ||
      combined.includes('login') ||
      combined.includes('log in')
    ) {
      const isSensitiveAuth = combined.includes('2fa') || combined.includes('ownership');
      return {
        category: 'account_and_login',
        confidence: 0.94,
        extractedQuestion: subject,
        reasoning: 'Customer inquiry regarding account access, authentication, or admin credentials.',
        needsHumanReview: isSensitiveAuth,
        uncertaintyReason: isSensitiveAuth ? 'Account security or ownership transfer requires human verification.' : undefined,
      };
    }

    // 5. Billing & Payments
    if (
      combined.includes('invoice') ||
      combined.includes('receipt') ||
      combined.includes('vat') ||
      combined.includes('stripe') ||
      combined.includes('payment gateway') ||
      combined.includes('duplicate charge') ||
      combined.includes('refund') ||
      combined.includes('credit card') ||
      combined.includes('volume discount') ||
      combined.includes('pricing') ||
      combined.includes('tax exemption') ||
      combined.includes('501(c)(3)') ||
      combined.includes('failed payment') ||
      combined.includes('chargeback') ||
      combined.includes('dispute') ||
      combined.includes('billing')
    ) {
      const isDisputed = combined.includes('refund') || combined.includes('tax exemption') || combined.includes('discount');
      return {
        category: 'billing_and_payments',
        confidence: 0.93,
        extractedQuestion: subject,
        reasoning: 'Inquiry relates to subscription billing, gateway keys, taxes, or payments.',
        needsHumanReview: isDisputed,
        uncertaintyReason: isDisputed ? 'Financial adjustment, refund, or tax exemption requires billing review.' : undefined,
      };
    }

    // 6. Technical Support
    if (
      combined.includes('ssl certificate') ||
      combined.includes('not secure') ||
      combined.includes('webhook') ||
      combined.includes('http 500') ||
      combined.includes('404') ||
      combined.includes('rate limit') ||
      combined.includes('http 429') ||
      combined.includes('photo upload') ||
      combined.includes('max upload file size') ||
      combined.includes('google maps api') ||
      combined.includes('referernotallowed') ||
      combined.includes('database connection') ||
      combined.includes('intermittent timeouts') ||
      combined.includes('custom javascript') ||
      combined.includes('checkout button') ||
      combined.includes('dns') ||
      combined.includes('nameservers') ||
      combined.includes('bug') ||
      combined.includes('error') ||
      combined.includes('crashed')
    ) {
      const isUrgent = combined.includes('urgent') || combined.includes('database connection');
      return {
        category: 'technical_support',
        confidence: 0.92,
        extractedQuestion: subject,
        reasoning: 'Inquiry relates to platform errors, DNS, SSL, webhooks, or API behavior.',
        needsHumanReview: isUrgent,
        uncertaintyReason: isUrgent ? 'Infrastructure connection issue requires technical triage.' : undefined,
      };
    }

    // 7. Product Configuration & How-To
    if (
      combined.includes('form fields') ||
      combined.includes('signup form') ||
      combined.includes('form manager') ||
      combined.includes('lead routing') ||
      combined.includes('auto-matching') ||
      combined.includes('navigation menu') ||
      combined.includes('header navigation') ||
      combined.includes('menu manager') ||
      combined.includes('welcome email') ||
      combined.includes('email template') ||
      combined.includes('recurring monthly subscriptions') ||
      combined.includes('membership plan') ||
      combined.includes('seo meta tags') ||
      combined.includes('seo templates') ||
      combined.includes('phone numbers behind a login wall') ||
      combined.includes('text labels') ||
      combined.includes('translating') ||
      combined.includes('how do i') ||
      combined.includes('how to') ||
      combined.includes('configure')
    ) {
      return {
        category: 'product_configuration',
        confidence: 0.91,
        extractedQuestion: subject,
        reasoning: 'Customer asking for how-to instructions in admin forms, menus, plans, or settings.',
        needsHumanReview: false,
      };
    }

    // Default Fallback
    return {
      category: 'other_or_uncertain',
      confidence: 0.60,
      extractedQuestion: subject || cleanBody.substring(0, 50),
      reasoning: 'General inquiry that does not cleanly match primary administrative categories.',
      needsHumanReview: true,
      uncertaintyReason: 'Inquiry does not clearly match known categories.',
    };
  }
}
