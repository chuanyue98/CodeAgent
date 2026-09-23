import request from '../utils/request';

export type DelegationStatus = 'starting' | 'running' | 'completed' | 'failed' | 'stopped' | 'unknown';

export interface DelegationResult {
  success: boolean;
  exitCode: number | null;
  summary: string;
  summaryTruncated: boolean;
  filesChanged: string[];
  diff: string;
  diffTruncated: boolean;
  branch: string | null;
  isolatedWorktree: boolean;
  durationSeconds: number;
  error: string | null;
}

export interface DelegationRun {
  runId: string;
  engine: string;
  mode: 'write' | 'review';
  status: DelegationStatus;
  instruction: string;
  workspace: string;
  outputLog: string;
  elapsedSeconds: number;
  error?: string;
}

export interface DelegationDetail extends DelegationRun {
  result?: DelegationResult;
  /** output.log 的末尾，进行中时用来看它在干什么。 */
  outputTail: string;
}

export async function fetchDelegations(): Promise<DelegationRun[]> {
  const body = await request<{ runs: DelegationRun[] }>('/api/delegations');
  return body.runs;
}

export function fetchDelegation(runId: string): Promise<DelegationDetail> {
  return request<DelegationDetail>(`/api/delegations/${encodeURIComponent(runId)}`);
}

export function stopDelegation(runId: string): Promise<unknown> {
  return request(`/api/delegations/${encodeURIComponent(runId)}/stop`, { method: 'POST' });
}
