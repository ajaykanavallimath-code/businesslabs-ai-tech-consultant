/**
 * Server entry point for Task 2: Inbox Agent REST API.
 */

import { createApp } from './app';
import { InboxAgent } from '../agents/inboxAgent';
import { config } from '../utils/config';
import { SafeLogger } from '../utils/logger';

export function startServer(port = config.port) {
  const agent = new InboxAgent();
  const app = createApp(agent);

  const server = app.listen(port, () => {
    SafeLogger.info(`Task 2 Inbox Agent API listening on http://localhost:${port}`);
    SafeLogger.info(`Knowledge Brain Base URL: ${config.kbBaseUrl}`);
    SafeLogger.info(`Autonomy Streak Requirement: ${config.autonomyStreakThreshold} consecutive unedited approvals`);
    SafeLogger.info(`Sending Mode: ${config.enableRealSending ? 'LIVE (Real Sending Enabled)' : 'SIMULATED (Safe Default)'}`);
  });

  return { app, server, agent };
}

if (require.main === module) {
  startServer();
}
