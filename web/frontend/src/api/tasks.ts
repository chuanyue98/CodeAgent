import request from '../utils/request';
import type { Engine, RunPollResponse, RunStatus, Task } from '../components/TaskDashboard/types';

/**
 * The task-board API surface in one module so the TanStack Query keys and
 * the endpoints they hit stay next to each other.
 */

export async function listTasks(): Promise<Task[]> {
  return request('/api/tasks');
}

export async function getTask(name: string, group?: string): Promise<Task> {
  const params = new URLSearchParams();
  if (group) params.append('group', group);
  return request(`/api/tasks/${name}?${params.toString()}`);
}

export async function createTask(body: {
  name: string;
  title: string;
  objective: string;
  context: string;
  instructions: string;
  verification: string;
}): Promise<Task> {
  return request('/api/tasks', { method: 'POST', body: JSON.stringify(body) });
}

export async function updateTask(name: string, content: string): Promise<Task> {
  return request(`/api/tasks/${name}`, {
    method: 'PUT',
    body: JSON.stringify({ content }),
  });
}

export async function deleteTask(name: string): Promise<void> {
  await request(`/api/tasks/${name}`, { method: 'DELETE' });
}

export async function generateTask(body: {
  engine: string;
  name: string;
  title: string;
  description: string;
}): Promise<{ taskId: string }> {
  return request('/api/tasks/generate', { method: 'POST', body: JSON.stringify(body) });
}

/** Runs the server process is currently tracking. */
export async function listRuns(): Promise<RunStatus[]> {
  return request('/api/tasks/runs');
}

/** Persisted run history for one task. */
export async function listTaskRuns(name: string): Promise<RunStatus[]> {
  return request(`/api/tasks/${name}/runs`);
}

export async function getRunStatus(taskId: string): Promise<RunPollResponse> {
  return request(`/api/tasks/runs/${taskId}`);
}

export async function runTask(
  name: string,
  body: { engine: string; group: string; workspace: string },
): Promise<RunStatus> {
  return request(`/api/tasks/${name}/run`, { method: 'POST', body: JSON.stringify(body) });
}

export async function stopRun(taskId: string): Promise<void> {
  await request(`/api/tasks/runs/${taskId}/stop`, { method: 'POST' });
}

export interface RunCommit {
  sha: string;
  message: string;
  author: string;
  committedAt: string;
}

export interface RunFileChange {
  path: string;
  additions: number | null;
  deletions: number | null;
}

export interface RunChangeEntry {
  status: string;
  path: string;
}

/**
 * Git changes attributed to one run. `available` is false (with a snake_case
 * `reason`) when the workspace cannot be inspected; otherwise `mode` is
 * "commits" (windowed commits + diff) or "uncommitted" (no commits landed in
 * the window, so the worktree state is shown instead).
 */
export interface RunChanges {
  available: boolean;
  reason?: string;
  workspace?: string | null;
  mode?: 'commits' | 'uncommitted';
  window?: { since: string; until: string };
  commits?: RunCommit[];
  files?: RunFileChange[];
  entries?: RunChangeEntry[];
  diff?: string;
  diffTruncated?: boolean;
  note?: string;
}

export async function getRunChanges(taskId: string): Promise<RunChanges> {
  return request(`/api/tasks/runs/${taskId}/changes`);
}

export async function listEngines(): Promise<Engine[]> {
  return request('/api/engines');
}
