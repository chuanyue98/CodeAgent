export interface Schedule {
  id: string;
  task_name: string;
  engine: string;
  group: string;
  cron_expr: string;
  enabled: boolean;
  created_at: number;
  last_run_at: number | null;
  last_run_status: string | null;
  next_run_at: number | null;
}

export interface CreateScheduleParams {
  task_name: string;
  engine: string;
  group?: string;
  cron_expr: string;
  enabled?: boolean;
}

import request from '../utils/request';

export interface UpdateScheduleParams {
  task_name?: string;
  engine?: string;
  group?: string;
  cron_expr?: string;
  enabled?: boolean;
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

export async function runScheduleNow(scheduleId: string): Promise<void> {
  await request(`/api/schedules/${encodeURIComponent(scheduleId)}/run-now`, {
    method: 'POST',
  });
}
