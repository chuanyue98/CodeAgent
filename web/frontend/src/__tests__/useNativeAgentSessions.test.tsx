import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, test, vi } from 'vitest';
import { fetchNativeAgentSessions } from '../api/agent';
import useNativeAgentSessions from '../pages/useNativeAgentSessions';
import type { NativeAgentSession } from '../types/agent';

vi.mock('../api/agent', () => ({
  fetchNativeAgentSessions: vi.fn(),
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

const session: NativeAgentSession = {
  session_id: 'session-1',
  engine: 'codex',
  project_path: '/workspace',
  started_at: '2026-07-18T00:00:00Z',
  ended_at: null,
  message_count: 1,
  title: 'Review',
  model: null,
};

describe('useNativeAgentSessions', () => {
  beforeEach(() => {
    vi.mocked(fetchNativeAgentSessions).mockReset();
  });

  test('ignores stale errors and loading cleanup after a forced refresh', async () => {
    const first = deferred<NativeAgentSession[]>();
    const second = deferred<NativeAgentSession[]>();
    vi.mocked(fetchNativeAgentSessions)
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    const { result } = renderHook(() => useNativeAgentSessions([], ''));

    act(() => {
      void result.current.loadNativeSessions('codex');
      void result.current.loadNativeSessions('codex', true);
    });
    await act(async () => {
      first.reject(new Error('stale failure'));
      await Promise.resolve();
    });

    expect(result.current.nativeSessionErrors.codex).toBeUndefined();
    expect(result.current.nativeLoadingProviders.has('codex')).toBe(true);

    await act(async () => {
      second.resolve([session]);
      await second.promise;
    });
    await waitFor(() => {
      expect(result.current.nativeSessionsByProvider.codex).toEqual([session]);
      expect(result.current.nativeLoadingProviders.has('codex')).toBe(false);
    });
  });

  test('does not restore a removed session from an older request', async () => {
    const request = deferred<NativeAgentSession[]>();
    vi.mocked(fetchNativeAgentSessions).mockReturnValueOnce(request.promise);
    const { result } = renderHook(() => useNativeAgentSessions([], ''));

    act(() => {
      void result.current.loadNativeSessions('codex');
      result.current.removeNativeSession('codex', 'session-1');
    });
    await act(async () => {
      request.resolve([session]);
      await request.promise;
    });

    expect(result.current.nativeSessionsByProvider.codex).toEqual([]);
  });
});
