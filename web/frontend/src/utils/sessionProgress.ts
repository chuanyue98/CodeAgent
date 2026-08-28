/**
 * Derives an at-a-glance progress summary from a parsed session transcript.
 *
 * The Sessions view had two extremes and nothing in between: the transcript,
 * which answers "what was said" only after you read it, and the Instances
 * page, which only knows about processes CodeAgent itself started. Neither
 * answers "how far did this session get" — which is the question you actually
 * have when you come back to a session you left running in another terminal.
 *
 * Everything here is computed from data the detail panel already fetched, so
 * no extra request is involved.
 */

import type { SessionDetail, SessionMessage } from '../api/audit';

/** Argument keys the four engines use to name a file operand. */
const FILE_KEYS = ['file_path', 'filePath', 'notebook_path', 'filename', 'path', 'file'];

/**
 * Matches a file-naming key in a JSON fragment, tolerating backslash escapes
 * so Windows paths (``"C:\\src\\app.ts"``) survive the capture intact.
 */
const FILE_KEY_PATTERN = new RegExp(
  `"(?:${FILE_KEYS.join('|')})"\\s*:\\s*"((?:[^"\\\\]|\\\\.)*)"`,
  'i',
);

export interface RecentAction {
  /** Tool name as the engine recorded it, e.g. ``Edit``, ``Bash``. */
  name: string;
  /** The file it acted on, or a trimmed argument preview when there is none. */
  detail: string;
}

export interface SessionProgress {
  /** User messages — one per thing you asked for. */
  turns: number;
  /** Wall-clock span of the transcript, or null when timestamps are missing. */
  durationMs: number | null;
  toolCalls: number;
  /** Distinct files named by any tool call, most recently touched first. */
  files: string[];
  /** Most recent tool calls, newest first. */
  recent: RecentAction[];
}

/** Unescapes a captured JSON string body; returns it as-is if that fails. */
function unescapeJsonString(raw: string): string {
  try {
    return JSON.parse(`"${raw}"`) as string;
  } catch {
    return raw;
  }
}

/**
 * Pulls the file path out of a tool call's argument preview.
 *
 * Parsers truncate ``args_preview`` at 200 characters, so a call with a long
 * argument list arrives as invalid JSON. The regex fallback exists for that
 * case: the key is usually well inside the first 200 characters even when the
 * closing brace is not.
 */
export function extractFilePath(argsPreview: string): string | null {
  const preview = argsPreview?.trim();
  if (!preview) return null;

  try {
    const parsed: unknown = JSON.parse(preview);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      for (const key of FILE_KEYS) {
        const value = (parsed as Record<string, unknown>)[key];
        if (typeof value === 'string' && value.trim()) return value.trim();
      }
      return null;
    }
  } catch {
    // Truncated preview — fall through to the scan.
  }

  const match = FILE_KEY_PATTERN.exec(preview);
  return match ? unescapeJsonString(match[1]).trim() || null : null;
}

function parseTime(timestamp: string): number | null {
  if (!timestamp) return null;
  const ms = Date.parse(timestamp);
  return Number.isNaN(ms) ? null : ms;
}

/** Trims an argument preview down to something that fits on one line. */
function shortArgs(argsPreview: string, limit = 60): string {
  const flat = argsPreview.replace(/\s+/g, ' ').trim();
  return flat.length > limit ? `${flat.slice(0, limit)}…` : flat;
}

export function formatDuration(ms: number | null): string | null {
  if (ms === null || ms < 0) return null;
  const totalSeconds = Math.round(ms / 1000);
  if (totalSeconds < 60) return `${totalSeconds}s`;
  const minutes = Math.floor(totalSeconds / 60);
  if (minutes < 60) return `${minutes}m`;
  return `${Math.floor(minutes / 60)}h${String(minutes % 60).padStart(2, '0')}m`;
}

export function summarizeSession(
  detail: Pick<SessionDetail, 'messages'> | null,
  recentLimit = 3,
): SessionProgress {
  const messages: SessionMessage[] = detail?.messages ?? [];

  let turns = 0;
  let toolCalls = 0;
  let firstTime: number | null = null;
  let lastTime: number | null = null;
  const recent: RecentAction[] = [];
  // Insertion order is oldest-first here and reversed on the way out, so the
  // "most recently touched first" ordering survives de-duplication.
  const files = new Set<string>();

  for (const message of messages) {
    if (message.role === 'user') turns += 1;

    const time = parseTime(message.timestamp);
    if (time !== null) {
      if (firstTime === null || time < firstTime) firstTime = time;
      if (lastTime === null || time > lastTime) lastTime = time;
    }

    for (const call of message.tool_calls ?? []) {
      toolCalls += 1;
      const path = extractFilePath(call.args_preview);
      if (path) {
        // Re-inserting would keep the original position, so drop first.
        files.delete(path);
        files.add(path);
      }
      recent.push({
        name: call.name || '—',
        detail: path ?? shortArgs(call.args_preview ?? ''),
      });
    }
  }

  return {
    turns,
    durationMs: firstTime !== null && lastTime !== null ? lastTime - firstTime : null,
    toolCalls,
    files: [...files].reverse(),
    recent: recent.slice(-recentLimit).reverse(),
  };
}
