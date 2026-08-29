import type { SessionUsage } from '../api/analytics';

/** A `SessionUsage` row with sane defaults; override only what a test asserts on. */
export function session(overrides: Partial<SessionUsage> = {}): SessionUsage {
  return {
    sessionId: 'session-a',
    target: 'claude',
    projectPath: '/workspace/project-a',
    inputTokens: 100,
    outputTokens: 50,
    cacheCreationTokens: 0,
    cacheReadTokens: 0,
    cost: 0.12,
    lastActivity: '2026-07-20T10:00:00Z',
    modelsUsed: ['claude-opus'],
    modelBreakdowns: [],
    ...overrides,
  };
}

/** A resolved `fetch` stub exposing both `text()` and `json()`, as the app reads either. */
export function jsonResponse(data: unknown) {
  return Promise.resolve({
    ok: true,
    status: 200,
    text: async () => JSON.stringify(data),
    json: async () => data,
  });
}
