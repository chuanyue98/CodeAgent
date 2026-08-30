import { describe, expect, test } from 'vitest';
import {
  extractFilePath,
  formatDuration,
  summarizeSession,
} from '../utils/sessionProgress';
import type { SessionMessage } from '../api/audit';

function msg(
  role: string,
  timestamp: string,
  toolCalls: SessionMessage['toolCalls'] = [],
): SessionMessage {
  return { role, content: '', timestamp, model: '', toolCalls };
}

function call(name: string, argsPreview: string) {
  return { name, argsPreview, resultPreview: '' };
}

describe('extractFilePath', () => {
  test('reads the path out of well-formed arguments', () => {
    expect(extractFilePath('{"file_path": "core/web/routers/history.py"}')).toBe(
      'core/web/routers/history.py',
    );
  });

  test('recovers the path from a preview truncated mid-JSON', () => {
    // The parsers cut argsPreview at 200 characters, so the closing brace is
    // routinely missing on a call with a long argument list.
    const truncated = `{"file_path": "core/services/agent_gateway.py", "old_string": "${'x'.repeat(160)}`;
    expect(extractFilePath(truncated)).toBe('core/services/agent_gateway.py');
  });

  test('unescapes a Windows path', () => {
    expect(extractFilePath('{"path": "C:\\\\src\\\\app.ts"}')).toBe('C:\\src\\app.ts');
  });

  test('returns null when no argument names a file', () => {
    expect(extractFilePath('{"command": ["pytest", "-q"]}')).toBeNull();
    expect(extractFilePath('')).toBeNull();
  });
});

describe('formatDuration', () => {
  test.each([
    [null, null],
    [45_000, '45s'],
    [12 * 60_000, '12m'],
    [(83 * 60 + 4) * 1000, '1h23m'],
  ])('formats %s', (ms, expected) => {
    expect(formatDuration(ms as number | null)).toBe(expected);
  });
});

describe('summarizeSession', () => {
  const detail = {
    messages: [
      msg('user', '2026-08-28T10:00:00Z'),
      msg('assistant', '2026-08-28T10:01:00Z', [
        call('Read', '{"file_path": "a.py"}'),
        call('Edit', '{"file_path": "b.py"}'),
      ]),
      msg('user', '2026-08-28T10:05:00Z'),
      msg('assistant', '2026-08-28T11:23:00Z', [
        call('Edit', '{"file_path": "a.py"}'),
        call('Bash', '{"command": "pytest -q"}'),
      ]),
    ],
  };

  test('counts user turns, tool calls and wall-clock span', () => {
    const progress = summarizeSession(detail);
    expect(progress.turns).toBe(2);
    expect(progress.toolCalls).toBe(4);
    expect(formatDuration(progress.durationMs)).toBe('1h23m');
  });

  test('de-duplicates files, most recently touched first', () => {
    // a.py is touched first and again last; it must appear once, at the front.
    expect(summarizeSession(detail).files).toEqual(['a.py', 'b.py']);
  });

  test('reports the most recent actions newest first', () => {
    const { recent } = summarizeSession(detail);
    // Only the last three of the four calls, so the opening Read drops out.
    expect(recent.map(a => a.name)).toEqual(['Bash', 'Edit', 'Edit']);
    expect(recent[0].detail).toBe('{"command": "pytest -q"}');
    expect(recent[1].detail).toBe('a.py');
    expect(recent[2].detail).toBe('b.py');
  });

  test('honours the recent-action limit', () => {
    expect(summarizeSession(detail, 1).recent.map(a => a.name)).toEqual(['Bash']);
  });

  test('survives a session with no messages', () => {
    const empty = summarizeSession(null);
    expect(empty).toEqual({
      turns: 0,
      durationMs: null,
      toolCalls: 0,
      files: [],
      recent: [],
    });
  });

  test('leaves duration null when timestamps are missing', () => {
    expect(summarizeSession({ messages: [msg('user', ''), msg('assistant', '')] }).durationMs).toBeNull();
  });
});
