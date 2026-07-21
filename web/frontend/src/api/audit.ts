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

import request from '../utils/request';

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
  return request(`/api/history/audit${qs ? `?${qs}` : ''}`);
}

export interface ConvertSessionParams {
  sourceEngine: string;
  sessionId: string;
  targetEngine: string;
  projectPath: string;
}

export interface ConvertSessionResult {
  status: string;
  new_session_id: string;
  target_engine: string;
  message?: string;
}

export interface ConvertAndLaunchResult extends ConvertSessionResult {
  terminal?: string;
}

function convertBody(params: ConvertSessionParams) {
  return JSON.stringify({
    source_engine: params.sourceEngine,
    session_id: params.sessionId,
    target_engine: params.targetEngine,
    project_path: params.projectPath,
  });
}

/** Converts a session to another engine's native format without launching it. */
export async function convertSession(
  params: ConvertSessionParams,
): Promise<ConvertSessionResult> {
  return request('/api/history/convert', { method: 'POST', body: convertBody(params) });
}

/** Converts a session and opens the target engine in a terminal for that project. */
export async function convertAndLaunchSession(
  params: ConvertSessionParams,
): Promise<ConvertAndLaunchResult> {
  return request('/api/history/convert-and-launch', {
    method: 'POST',
    body: convertBody(params),
  });
}
