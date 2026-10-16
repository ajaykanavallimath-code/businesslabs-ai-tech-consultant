/**
 * Typed client for Task 1 Knowledge Brain REST API.
 * Calls POST /api/v1/query to retrieve grounded citations and screenshots.
 */

import { KnowledgeBrainResponse } from '../models/types';
import { AgentConfig, config as globalConfig } from '../utils/config';
import { SafeLogger } from '../utils/logger';

export interface KBClientOptions {
  config?: AgentConfig;
  customFetch?: typeof fetch;
}

export class KnowledgeBrainClient {
  private config: AgentConfig;
  private fetchFn: typeof fetch;

  constructor(options?: KBClientOptions | AgentConfig) {
    if (options && 'kbApiUrl' in options) {
      this.config = options;
      this.fetchFn = fetch;
    } else {
      this.config = (options as KBClientOptions)?.config || globalConfig;
      this.fetchFn = (options as KBClientOptions)?.customFetch || fetch;
    }
  }

  /**
   * Alias for queryKnowledgeBase
   */
  async query(
    queryText: string,
    topK = 3,
    minScore?: number
  ): Promise<KnowledgeBrainResponse> {
    return this.queryKnowledgeBase(queryText, topK, minScore);
  }

  /**
   * Check if Knowledge Brain service is reachable and healthy.
   */
  async checkHealth(): Promise<boolean> {
    const url = `${this.config.kbApiUrl}/api/v1/health`;
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 2000);

      const resp = await this.fetchFn(url, {
        method: 'GET',
        signal: controller.signal,
      });
      clearTimeout(timeout);
      return resp.ok;
    } catch {
      return false;
    }
  }

  /**
   * Query the Knowledge Brain with a customer inquiry.
   */
  async queryKnowledgeBase(
    queryText: string,
    topK = 3,
    minScore?: number
  ): Promise<KnowledgeBrainResponse> {
    const cleanQuery = queryText.trim();
    if (!cleanQuery) {
      return this.buildFallbackResponse(
        queryText,
        'Empty query provided; cannot search documentation.',
        true
      );
    }

    if (this.config.mockKb) {
      return this.getMockResponse(cleanQuery);
    }

    // If running in explicit mock LLM mode and server is unreachable, use deterministic mock
    if (this.config.mockLlm) {
      const isHealthy = await this.checkHealth();
      if (!isHealthy) {
        return this.getMockResponse(cleanQuery);
      }
    }

    const endpoint = `${this.config.kbApiUrl}/api/v1/query`;
    const payload = {
      query: cleanQuery,
      top_k: topK,
      min_score: minScore,
    };

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), this.config.kbTimeoutMs);

      const response = await this.fetchFn(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
        },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        SafeLogger.warn(
          `Knowledge Brain API error: HTTP ${response.status} ${response.statusText}`
        );
        return this.buildFallbackResponse(
          cleanQuery,
          `Knowledge Brain service returned HTTP ${response.status}.`,
          true
        );
      }

      const data = (await response.json()) as KnowledgeBrainResponse;
      return data;
    } catch (err: unknown) {
      const isTimeout = (err as Error)?.name === 'AbortError';
      const reason = isTimeout
        ? `Knowledge Brain request timed out after ${this.config.kbTimeoutMs}ms.`
        : `Knowledge Brain connection error: ${(err as Error)?.message || 'Service unavailable'}.`;

      SafeLogger.warn(`KB query failed for "${cleanQuery}": ${reason}`);

      // If mock mode is active, fall back to mock response on network error
      if (this.config.mockLlm) {
        return this.getMockResponse(cleanQuery);
      }

      return this.buildFallbackResponse(cleanQuery, reason, true);
    }
  }

  /**
   * Deterministic mock response for offline testing.
   */
  private getMockResponse(query: string): KnowledgeBrainResponse {
    const q = query.toLowerCase();

    // Out-of-scope or unsupported topics trigger escalation
    if (
      q.includes('quantum') ||
      q.includes('unsupported') ||
      q.includes('illegal') ||
      q.includes('hack') ||
      q.includes('refund dispute') ||
      q.includes('wordpress') ||
      q.includes('php code') ||
      q.includes('modify core')
    ) {
      return {
        query,
        answer: 'I could not find verified Brilliant Directories documentation for this topic. Escalated to human expert.',
        confidence_score: 0.15,
        escalated: true,
        escalation_id: `esc_mock_${Date.now().toString(36)}`,
        sources: [],
        images: [],
      };
    }

    // Domain & DNS settings
    if (q.includes('domain') || q.includes('dns') || q.includes('cname') || q.includes('a record')) {
      return {
        query,
        answer: 'To connect your live domain, navigate to Settings > Domain Manager in your admin dashboard. Enter your custom domain and point your DNS A Record to the Brilliant Directories server IP.',
        confidence_score: 0.94,
        escalated: false,
        escalation_id: null,
        sources: [
          {
            title: 'Guide 1. How to Connect a Live Domain Name',
            url: 'https://support.brilliantdirectories.com/support/solutions/articles/12000065940-guide-1-how-to-connect-a-live-domain-name',
            snippet: 'The current Domain Manager guides the entire connection through up to four stages: Choose An Address, Check It, Point Domain, and Switch Over.',
            score: 0.88,
            section: 'Domain Setup',
            images: [
              {
                url: 'https://s3.amazonaws.com/cdn.freshdesk.com/data/helpdesk/attachments/production/12185668534/original/woU8C814_2yX08ziBJcQcO-54kLJi2FC_g.png?1790182288',
                caption: 'Domain Manager wizard setup screen',
              },
            ],
          },
        ],
        images: [
          {
            url: 'https://s3.amazonaws.com/cdn.freshdesk.com/data/helpdesk/attachments/production/12185668534/original/woU8C814_2yX08ziBJcQcO-54kLJi2FC_g.png?1790182288',
            caption: 'Domain Manager wizard setup screen',
          },
        ],
      };
    }

    // Membership plans
    if (q.includes('membership') || q.includes('pricing') || q.includes('tier') || q.includes('billing frequency')) {
      return {
        query,
        answer: 'You can manage membership tiers in Finance > Membership Plans. From here you can configure pricing, renewal frequencies (monthly/annual), and profile publishing privileges.',
        confidence_score: 0.92,
        escalated: false,
        escalation_id: null,
        sources: [
          {
            title: 'Finance: Membership Plans Management',
            url: 'https://support.brilliantdirectories.com/support/solutions/articles/12000078901-membership-plans',
            snippet: 'Navigate to Finance > Membership Plans to create, edit, or clone member pricing tiers.',
            score: 0.85,
            section: 'Finance > Membership Plans',
            images: [],
          },
        ],
        images: [],
      };
    }

    // Webhooks & API
    if (q.includes('webhook') || q.includes('api key') || q.includes('zapier')) {
      return {
        query,
        answer: 'Webhooks can be configured under Developer Hub > Webhooks. Brilliant Directories supports outbound webhooks with HMAC SHA-256 signature verification.',
        confidence_score: 0.90,
        escalated: false,
        escalation_id: null,
        sources: [
          {
            title: 'Developer Hub: Webhooks & API Integration',
            url: 'https://support.brilliantdirectories.com/support/solutions/articles/12000089012-webhooks',
            snippet: 'Configure event-driven webhooks for member signups, billing updates, and form submissions in Developer Tools > Webhooks.',
            score: 0.83,
            section: 'Developer Hub',
            images: [],
          },
        ],
        images: [],
      };
    }

    // Generic support hit
    return {
      query,
      answer: 'General Solution Center guidance is available in your Brilliant Directories admin dashboard under Settings and Toolbox.',
      confidence_score: 0.75,
      escalated: false,
      escalation_id: null,
      sources: [
        {
          title: 'Brilliant Directories Support Overview',
          url: 'https://support.brilliantdirectories.com/support/solutions',
          snippet: 'Access comprehensive guides, video tutorials, and technical reference manuals.',
          score: 0.72,
          images: [],
        },
      ],
      images: [],
    };
  }

  private buildFallbackResponse(
    query: string,
    reason: string,
    escalate: boolean
  ): KnowledgeBrainResponse {
    return {
      query,
      answer: `Knowledge retrieval unavailable: ${reason}`,
      confidence_score: 0.0,
      escalated: escalate,
      escalation_id: null,
      sources: [],
      images: [],
    };
  }
}
