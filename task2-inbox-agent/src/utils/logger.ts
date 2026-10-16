/**
 * Safe logger for Task 2: Inbox Agent
 * Automatically masks API keys, bearer tokens, and secrets from all log output.
 */

export class SafeLogger {
  private static maskSecrets(message: string): string {
    return message
      .replace(/sk-ant-[a-zA-Z0-9_\-]+/g, 'sk-ant-***REDACTED***')
      .replace(/Bearer\s+[a-zA-Z0-9_\.\-]+/gi, 'Bearer ***REDACTED***')
      .replace(/api[_-]?key["']?\s*[:=]\s*["']?[^"',\s]+/gi, 'api_key=***REDACTED***');
  }

  static info(message: string, ...args: unknown[]): void {
    console.log(`[INFO] ${this.maskSecrets(message)}`, ...args);
  }

  static warn(message: string, ...args: unknown[]): void {
    console.warn(`[WARN] ${this.maskSecrets(message)}`, ...args);
  }

  static error(message: string, ...args: unknown[]): void {
    console.error(`[ERROR] ${this.maskSecrets(message)}`, ...args);
  }

  static debug(message: string, ...args: unknown[]): void {
    if (process.env.LOG_LEVEL?.toUpperCase() === 'DEBUG') {
      console.debug(`[DEBUG] ${this.maskSecrets(message)}`, ...args);
    }
  }
}
