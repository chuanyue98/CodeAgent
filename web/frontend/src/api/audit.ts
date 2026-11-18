import request from '../utils/request';

export interface SessionMessage {
  role: string;
  content: string;
  timestamp: string;
  model: string;
  toolCalls: { name: string; argsPreview: string; resultPreview: string }[];
}

export interface SessionDetail {
  sessionId: string;
  engine: string;
  projectPath: string;
  title: string;
  messages: SessionMessage[];
}

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

interface ConvertSessionParams {
  sourceEngine: string;
  sessionId?: string;
  targetEngine: string;
  projectPath: string;
}

interface ConvertSessionResult {
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

interface ConvertAndLaunchResult extends ConvertSessionResult, ResumeTarget {}

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
