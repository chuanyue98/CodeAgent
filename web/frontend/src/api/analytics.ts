export interface ModelBreakdown {
  modelName: string;
  inputTokens: number;
  outputTokens: number;
  cacheCreationTokens: number;
  cacheReadTokens: number;
  cost: number;
}

export interface DailyUsage {
  date: string;
  target: string;
  inputTokens: number;
  outputTokens: number;
  cacheCreationTokens: number;
  cacheReadTokens: number;
  cost: number;
  modelsUsed: string[];
  modelBreakdowns: ModelBreakdown[];
}

export interface MonthlyUsage {
  month: string;
  target: string;
  inputTokens: number;
  outputTokens: number;
  cacheCreationTokens: number;
  cacheReadTokens: number;
  cost: number;
  modelsUsed: string[];
  modelBreakdowns: ModelBreakdown[];
}

export interface SessionUsage {
  sessionId: string;
  target: string;
  projectPath: string;
  /** Session title joined from native history (may be empty). */
  title?: string;
  inputTokens: number;
  outputTokens: number;
  cacheCreationTokens: number;
  cacheReadTokens: number;
  cost: number;
  lastActivity: string;
  modelsUsed: string[];
  modelBreakdowns: ModelBreakdown[];
}

export interface EngineSummary {
  target: string;
  inputTokens: number;
  outputTokens: number;
  cacheCreationTokens: number;
  cacheReadTokens: number;
  cost: number;
  sessionCount: number;
  models: string[];
}

export interface AnalyticsSummary {
  total_entries: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cache_creation_tokens: number;
  total_cache_read_tokens: number;
  targets: string[];
  models: string[];
  session_count: number;
}

import request from '../utils/request';

export async function fetchSummary(): Promise<AnalyticsSummary> {
  return request('/api/analytics/summary');
}

export async function fetchDaily(): Promise<DailyUsage[]> {
  return request('/api/analytics/daily');
}

export async function fetchMonthly(): Promise<MonthlyUsage[]> {
  return request('/api/analytics/monthly');
}

export interface SessionPage {
  sessions: SessionUsage[];
  /** Pass back as `cursor` for the next page; null when this was the last. */
  nextCursor: string | null;
  /** How many sessions match the filters, ignoring the page size. */
  total: number;
}

export interface SessionPageParams {
  limit?: number;
  project?: string;
  /** Matched server-side against title, id, project path and engine. */
  search?: string;
  cursor?: string | null;
}

/** One page of sessions, with the cursor for the next. */
export async function fetchSessionPage({
  limit = 100,
  project,
  search,
  cursor,
}: SessionPageParams = {}): Promise<SessionPage> {
  const query = new URLSearchParams({ limit: String(limit) });
  if (project) query.set('project', project);
  if (search) query.set('search', search);
  if (cursor) query.set('cursor', cursor);
  return request(`/api/analytics/sessions?${query}`);
}

/**
 * The first page as a plain array, for callers that only ever wanted the most
 * recent handful (the home page, the command palette, the usage totals).
 */
export async function fetchSessions(limit = 100, project?: string): Promise<SessionUsage[]> {
  const page = await fetchSessionPage({ limit, project });
  return page.sessions;
}

export async function fetchEngines(): Promise<EngineSummary[]> {
  return request('/api/analytics/engines');
}

export interface ModelStat {
  model: string;
  inputTokens: number;
  outputTokens: number;
  cacheCreationTokens: number;
  cacheReadTokens: number;
  inputCost: number;
  outputCost: number;
  cacheWriteCost: number;
  cacheReadCost: number;
  cost: number;
  sessionCount: number;
  targets: string[];
}

export async function fetchModels(): Promise<ModelStat[]> {
  return request('/api/analytics/models');
}

export async function refreshAnalytics(): Promise<void> {
  await request('/api/analytics/refresh', { method: 'POST' });
}

export function fmtTokens(n: number): string {
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)}B`;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

export function fmtCost(n: number): string {
  if (n === 0) return '$0';
  if (n < 0.01) return `$${n.toFixed(4)}`;
  return `$${n.toFixed(2)}`;
}
