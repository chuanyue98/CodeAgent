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

export interface SessionMessage {
  role: string;
  content: string;
  timestamp: string;
  model: string;
  tool_calls: { name: string; args_preview: string; result_preview: string }[];
}

export interface SessionDetail {
  session_id: string;
  engine: string;
  project_path: string;
  title: string;
  messages: SessionMessage[];
}

import request from '../utils/request';

/** Full transcript of one session, including tool calls per message. */
export async function fetchSessionDetail(
  engine: string,
  sessionId: string,
  project: string,
): Promise<SessionDetail> {
  const query = new URLSearchParams({ project });
  return request(
    `/api/history/${encodeURIComponent(engine)}/${encodeURIComponent(sessionId)}?${query}`,
  );
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
  newSessionId: string;
  targetEngine: string;
  message?: string;
}

/**
 * Where to attach a browser terminal. Nothing has been started yet -- the
 * websocket spawns the engine when the terminal opens. This used to report a
 * GUI terminal the server had opened on its own desktop, which was unreachable
 * whenever the browser was somewhere else.
 */
export interface ResumeTarget {
  engine: string;
  sessionId: string;
  project: string;
}

export interface ConvertAndLaunchResult extends ConvertSessionResult, ResumeTarget {}

/** Asks where to resume an existing session; starts nothing by itself. */
export async function continueSession(
  engine: string,
  sessionId: string,
  projectPath: string,
): Promise<ResumeTarget & { status: string }> {
  const query = new URLSearchParams({ project: projectPath });
  return request(
    `/api/history/${encodeURIComponent(engine)}/${encodeURIComponent(sessionId)}/continue?${query}`,
    { method: 'POST' },
  );
}

function convertBody(params: ConvertSessionParams) {
  return JSON.stringify({
    sourceEngine: params.sourceEngine,
    sessionId: params.sessionId,
    targetEngine: params.targetEngine,
    projectPath: params.projectPath,
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

/** Permanently deletes one session's native history file. There is no undo. */
export async function deleteHistorySession(
  engine: string,
  sessionId: string,
  projectPath: string,
): Promise<{ status: string; sessionId: string }> {
  const query = new URLSearchParams({ project: projectPath });
  return request(
    `/api/history/${encodeURIComponent(engine)}/${encodeURIComponent(sessionId)}?${query}`,
    { method: 'DELETE' },
  );
}
