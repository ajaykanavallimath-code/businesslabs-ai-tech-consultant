/**
 * Configuration manager for Task 2: Inbox Agent
 */

import * as path from 'path';
import * as dotenv from 'dotenv';

// Attempt to load .env from project root, then local directory
const rootEnvPath = path.resolve(__dirname, '../../../.env');
dotenv.config({ path: rootEnvPath });
dotenv.config(); // fallback to current working directory .env

export interface AgentConfig {
  kbApiUrl: string;
  kbBaseUrl?: string;
  kbTimeoutMs: number;
  anthropicApiKey: string;
  anthropicModel?: string;
  claudeModelPrimary: string;
  claudeModelFast: string;
  mockLlm: boolean;
  mockKb?: boolean;
  autonomyStreakThreshold: number;
  qualityWindowSize: number;
  qualityMaxEditRate: number;
  qualityMaxRejectionRate: number;
  maxAllowedEditRate?: number;
  maxAllowedRejectionRate?: number;
  enableRealSending: boolean;
  storageDir: string;
  port: number;
  logLevel?: string;
}

export function loadConfig(overrides?: Partial<AgentConfig>): AgentConfig {
  const env = process.env;
  const mockLlmEnv = env.MOCK_LLM?.toLowerCase() === 'true';
  const mockKbEnv = env.MOCK_KB?.toLowerCase() === 'true';
  const apiKey = env.ANTHROPIC_API_KEY?.trim() || '';
  const isInvalidOrPlaceholder = !apiKey || apiKey.includes('your_') || apiKey.length < 20;

  const kbUrl =
    overrides?.kbApiUrl ||
    overrides?.kbBaseUrl ||
    env.KB_API_URL?.trim() ||
    env.KB_BASE_URL?.trim() ||
    'http://127.0.0.1:8000';

  const maxEdit = overrides?.maxAllowedEditRate ?? overrides?.qualityMaxEditRate ?? 0.2;
  const maxRej = overrides?.maxAllowedRejectionRate ?? overrides?.qualityMaxRejectionRate ?? 0.05;

  return {
    kbApiUrl: kbUrl,
    kbBaseUrl: kbUrl,
    kbTimeoutMs: overrides?.kbTimeoutMs ?? parseInt(env.KB_TIMEOUT_MS || '8000', 10),
    anthropicApiKey: apiKey,
    anthropicModel: overrides?.anthropicModel || env.ANTHROPIC_MODEL?.trim() || 'claude-3-5-sonnet-20241022',
    claudeModelPrimary: env.CLAUDE_MODEL_PRIMARY?.trim() || 'claude-3-5-sonnet-20241022',
    claudeModelFast: env.CLAUDE_MODEL_FAST?.trim() || 'claude-3-haiku-20240307',
    // Safe default: use mock LLM if explicitly requested OR if API key is not configured or placeholder
    mockLlm: overrides?.mockLlm !== undefined ? overrides.mockLlm : (mockLlmEnv || isInvalidOrPlaceholder),
    mockKb: overrides?.mockKb !== undefined ? overrides.mockKb : (mockKbEnv || false),
    autonomyStreakThreshold: overrides?.autonomyStreakThreshold ?? 20, // Strict capstone requirement: exactly 20 consecutive approvals
    qualityWindowSize: overrides?.qualityWindowSize ?? 10,       // Rolling window of recent reviews per category
    qualityMaxEditRate: maxEdit,    // Withdraw if > 20% of recent drafts required edits
    qualityMaxRejectionRate: maxRej, // Withdraw if any rejection occurs (>= 1 in window of 10)
    maxAllowedEditRate: maxEdit,
    maxAllowedRejectionRate: maxRej,
    enableRealSending: overrides?.enableRealSending !== undefined ? overrides.enableRealSending : (env.ENABLE_REAL_EMAIL_SENDING?.toLowerCase() === 'true'),
    storageDir: overrides?.storageDir || env.INBOX_STORAGE_DIR || path.resolve(__dirname, '../../data'),
    port: overrides?.port ?? parseInt(env.INBOX_PORT || '3000', 10),
    logLevel: overrides?.logLevel || env.LOG_LEVEL || 'info',
    ...overrides,
  };
}

export const config = loadConfig();
