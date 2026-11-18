import request from '../utils/request';
import type { RunStatus } from '../components/TaskDashboard/types';

export interface Schedule {
  id: string;
  taskName: string;
  engine: string;
  group: string;
  workspace: string | null;
  cronExpr: string;
  enabled: boolean;
  createdAt: number;
  lastRunAt: number | null;
  lastRunStatus: string | null;
  nextRunAt: number | null;
  notifyOn?: 'always' | 'success' | 'failure' | 'never';
  createdFromInput?: string | null;
}

export interface CreateScheduleParams {
  taskName: string;
  engine: string;
  group?: string;
  workspace: string;
  cronExpr: string;
  enabled?: boolean;
  notifyOn?: 'always' | 'success' | 'failure' | 'never';
  createdFromInput?: string | null;
}

export interface UpdateScheduleParams {
  taskName?: string;
  engine?: string;
  group?: string;
  workspace?: string;
  cronExpr?: string;
  enabled?: boolean;
  notifyOn?: 'always' | 'success' | 'failure' | 'never';
  createdFromInput?: string | null;
}

export interface ParsedTask {
  name: string;
  title: string;
  objective: string;
  context: string;
  instructions: string;
  verification: string;
}

export interface ParsedScheduleResult {
  cronExpr: string;
  cronDescription: string;
  nextRuns: number[];
  task: ParsedTask;
  rawOutput?: string | null;
}

export interface SchedulePreviewResult {
  valid: boolean;
  nextRuns: number[];
  error?: string | null;
}

export async function parseSchedule(
  input: string,
  engine: string,
): Promise<ParsedScheduleResult> {
  return request('/api/schedules/parse', {
    method: 'POST',
    body: JSON.stringify({ input, engine }),
    timeout: 130_000,
  });
}

export async function previewSchedule(cronExpr: string): Promise<SchedulePreviewResult> {
  return request(`/api/schedules/preview?cron_expr=${encodeURIComponent(cronExpr)}`);
}

export async function fetchSchedules(): Promise<Schedule[]> {
  return request('/api/schedules');
}

export async function createSchedule(params: CreateScheduleParams): Promise<Schedule> {
  return request('/api/schedules', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

export async function updateSchedule(
  scheduleId: string,
  params: UpdateScheduleParams,
): Promise<Schedule> {
  return request(`/api/schedules/${encodeURIComponent(scheduleId)}`, {
    method: 'PATCH',
    body: JSON.stringify(params),
  });
}

export async function deleteSchedule(scheduleId: string): Promise<void> {
  await request(`/api/schedules/${encodeURIComponent(scheduleId)}`, {
    method: 'DELETE',
  });
}

export async function runScheduleNow(scheduleId: string): Promise<RunStatus> {
  return request(`/api/schedules/${encodeURIComponent(scheduleId)}/run-now`, {
    method: 'POST',
  });
}
