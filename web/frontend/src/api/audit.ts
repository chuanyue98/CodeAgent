export type AuditEventType = 'message' | 'tool_call';

export interface AuditEvent {
  event_id: string;
  event_type: AuditEventType;
  engine: string;
  project_path: string;
  session_id: string;
  session_title: string;
  timestamp: string;
  role: string;
  model: string;
  // message events only
  content_preview?: string;
  // tool_call events only
  tool_name?: string;
  args_preview?: string;
  result_preview?: string;
}

export interface AuditEventsResponse {
  events: AuditEvent[];
  count: number;
}

export interface FetchAuditEventsParams {
  engine?: string;
  project?: string;
  since?: string;
  until?: string;
  limit?: number;
}

export async function fetchAuditEvents(
  params: FetchAuditEventsParams = {},
): Promise<AuditEventsResponse> {
  const query = new URLSearchParams();
  if (params.engine) query.set('engine', params.engine);
  if (params.project) query.set('project', params.project);
  if (params.since) query.set('since', params.since);
  if (params.until) query.set('until', params.until);
  if (params.limit) query.set('limit', String(params.limit));

  const qs = query.toString();
  const res = await fetch(`/api/history/audit${qs ? `?${qs}` : ''}`);
  if (!res.ok) throw new Error('Failed to fetch audit events');
  return res.json();
}
