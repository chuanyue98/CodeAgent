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
}

export interface CreateScheduleParams {
  taskName: string;
  engine: string;
  group?: string;
  workspace: string;
  cronExpr: string;
  enabled?: boolean;
}

import request from '../utils/request';

export interface UpdateScheduleParams {
  taskName?: string;
  engine?: string;
  group?: string;
  workspace?: string;
  cronExpr?: string;
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
