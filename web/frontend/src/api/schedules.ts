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

export interface UpdateScheduleParams {
  task_name?: string;
  engine?: string;
  group?: string;
  cron_expr?: string;
  enabled?: boolean;
}

async function handleResponse<T>(res: Response, fallbackMessage: string): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || fallbackMessage);
  }
  return res.json();
}

export async function fetchSchedules(): Promise<Schedule[]> {
  const res = await fetch('/api/schedules');
  return handleResponse(res, 'Failed to fetch schedules');
}

export async function createSchedule(params: CreateScheduleParams): Promise<Schedule> {
  const res = await fetch('/api/schedules', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  return handleResponse(res, 'Failed to create schedule');
}

export async function updateSchedule(
  scheduleId: string,
  params: UpdateScheduleParams,
): Promise<Schedule> {
  const res = await fetch(`/api/schedules/${encodeURIComponent(scheduleId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  return handleResponse(res, 'Failed to update schedule');
}

export async function deleteSchedule(scheduleId: string): Promise<void> {
  const res = await fetch(`/api/schedules/${encodeURIComponent(scheduleId)}`, {
    method: 'DELETE',
  });
  await handleResponse(res, 'Failed to delete schedule');
}

export async function runScheduleNow(scheduleId: string): Promise<void> {
  const res = await fetch(`/api/schedules/${encodeURIComponent(scheduleId)}/run-now`, {
    method: 'POST',
  });
  await handleResponse(res, 'Failed to run schedule');
}
