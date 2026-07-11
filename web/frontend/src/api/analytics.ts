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

export interface ModelBreakdown {
  modelName: string;
  inputTokens: number;
  outputTokens: number;
  cacheCreationTokens: number;
  cacheReadTokens: number;
  cost: number;
}

export interface SessionUsage {
  sessionId: string;
  target: string;
  projectPath: string;
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

export async function fetchSummary(): Promise<AnalyticsSummary> {
  const res = await fetch('/api/analytics/summary');
  if (!res.ok) throw new Error('Failed to fetch analytics summary');
  return res.json();
}

export async function fetchDaily(): Promise<DailyUsage[]> {
  const res = await fetch('/api/analytics/daily');
  if (!res.ok) throw new Error('Failed to fetch daily usage');
  return res.json();
}

export async function fetchMonthly(): Promise<MonthlyUsage[]> {
  const res = await fetch('/api/analytics/monthly');
  if (!res.ok) throw new Error('Failed to fetch monthly usage');
  return res.json();
}

export async function fetchSessions(limit = 100): Promise<SessionUsage[]> {
  const res = await fetch(`/api/analytics/sessions?limit=${limit}`);
  if (!res.ok) throw new Error('Failed to fetch sessions');
  return res.json();
}

export async function fetchEngines(): Promise<EngineSummary[]> {
  const res = await fetch('/api/analytics/engines');
  if (!res.ok) throw new Error('Failed to fetch engine summary');
  return res.json();
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
  const res = await fetch('/api/analytics/models');
  if (!res.ok) throw new Error('Failed to fetch model stats');
  return res.json();
}

export async function refreshAnalytics(): Promise<void> {
  const res = await fetch('/api/analytics/refresh', { method: 'POST' });
  if (!res.ok) throw new Error('Failed to refresh analytics');
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
