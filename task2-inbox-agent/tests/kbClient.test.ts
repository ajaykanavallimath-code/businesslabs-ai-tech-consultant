/**
 * Tests for Knowledge Brain Client Integration
 */

import { KnowledgeBrainClient } from '../src/services/kbClient';
import { AgentConfig, loadConfig } from '../src/utils/config';

describe('KnowledgeBrainClient', () => {
  let client: KnowledgeBrainClient;
  let testConfig: AgentConfig;

  beforeEach(() => {
    testConfig = loadConfig({
      port: 3001,
      mockLlm: true,
      mockKb: true,
      kbTimeoutMs: 1000,
      logLevel: 'error',
    });
    client = new KnowledgeBrainClient(testConfig);
  });

  it('retrieves relevant sources with titles, URLs, and image citations in mock mode', async () => {
    const res = await client.query('How do I connect my custom domain and configure DNS nameservers?');
    expect(res.escalated).toBe(false);
    expect(res.confidence_score).toBeGreaterThan(0.7);
    expect(res.sources.length).toBeGreaterThan(0);

    const firstSource = res.sources[0];
    expect(firstSource.title).toBeDefined();
    expect(firstSource.url).toMatch(/^https?:\/\//);
    expect(firstSource.snippet).toBeDefined();
    expect(firstSource.score).toBeGreaterThan(0);
  });

  it('escalates and lowers confidence for unknown or unsupported questions', async () => {
    const res = await client.query('Can you install WordPress plugins or modify core PHP code on the server?');
    expect(res.escalated).toBe(true);
    expect(res.confidence_score).toBeLessThanOrEqual(0.6);
  });

  it('falls back to mock response safely when live KB endpoint times out or is unreachable', async () => {
    // Force live mode to invalid URL to verify safe fallback
    const liveClient = new KnowledgeBrainClient(
      loadConfig({
        mockKb: false,
        mockLlm: true,
        kbBaseUrl: 'http://127.0.0.1:9999',
        kbApiUrl: 'http://127.0.0.1:9999',
        kbTimeoutMs: 200,
      })
    );

    const res = await liveClient.query('How to configure SSL?');
    expect(res).toBeDefined();
    expect(res.sources.length).toBeGreaterThan(0);
    expect(res.sources[0].url).toBeDefined();
  });

  it('handles empty query without crashing', async () => {
    const res = await client.query('');
    expect(res).toBeDefined();
    expect(res.answer).toBeDefined();
  });
});
