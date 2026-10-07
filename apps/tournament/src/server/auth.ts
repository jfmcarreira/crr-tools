import { createHmac, timingSafeEqual } from 'node:crypto';
import type { FastifyRequest } from 'fastify';

export const SESSION_COOKIE_NAME = 'tournament_admin_session';

export interface AuthenticationConfig {
  adminPassword: string;
  sessionSecret: string;
  sessionLifetimeMs?: number;
}

interface SessionPayload {
  expiresAt: number;
}

function constantTimeEquals(actual: string, expected: string): boolean {
  const actualBuffer = Buffer.from(actual);
  const expectedBuffer = Buffer.from(expected);
  return actualBuffer.length === expectedBuffer.length && timingSafeEqual(actualBuffer, expectedBuffer);
}

function sign(payload: string, secret: string): string {
  return createHmac('sha256', secret).update(payload).digest('base64url');
}

export function createSessionToken(config: AuthenticationConfig, now = Date.now()): string {
  const payload = Buffer.from(JSON.stringify({
    expiresAt: now + (config.sessionLifetimeMs ?? 7 * 24 * 60 * 60 * 1000),
  } satisfies SessionPayload)).toString('base64url');
  return `${payload}.${sign(payload, config.sessionSecret)}`;
}

export function isValidSessionToken(token: string | undefined, config: AuthenticationConfig, now = Date.now()): boolean {
  if (!token) {
    return false;
  }
  const separatorIndex = token.indexOf('.');
  if (separatorIndex < 1 || separatorIndex !== token.lastIndexOf('.')) {
    return false;
  }
  const payload = token.slice(0, separatorIndex);
  const signature = token.slice(separatorIndex + 1);
  if (!constantTimeEquals(signature, sign(payload, config.sessionSecret))) {
    return false;
  }
  try {
    const decoded = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8')) as SessionPayload;
    return Number.isFinite(decoded.expiresAt) && decoded.expiresAt > now;
  } catch {
    return false;
  }
}

export function passwordMatches(password: string, expectedPassword: string): boolean {
  return constantTimeEquals(password, expectedPassword);
}

export function isSecureRequest(request: FastifyRequest): boolean {
  return request.protocol === 'https';
}

interface LoginAttempt {
  failures: number;
  resetAt: number;
}

/** Small in-memory limiter. A process restart deliberately resets it. */
export class LoginRateLimiter {
  private readonly attempts = new Map<string, LoginAttempt>();

  public constructor(
    private readonly maximumFailures = 5,
    private readonly windowMs = 15 * 60 * 1000,
  ) {}

  public isLimited(key: string, now = Date.now()): boolean {
    const attempt = this.attempts.get(key);
    if (!attempt) {
      return false;
    }
    if (attempt.resetAt <= now) {
      this.attempts.delete(key);
      return false;
    }
    return attempt.failures >= this.maximumFailures;
  }

  public recordFailure(key: string, now = Date.now()): void {
    const previous = this.attempts.get(key);
    if (!previous || previous.resetAt <= now) {
      this.attempts.set(key, { failures: 1, resetAt: now + this.windowMs });
      return;
    }
    previous.failures += 1;
  }

  public clear(key: string): void {
    this.attempts.delete(key);
  }
}
