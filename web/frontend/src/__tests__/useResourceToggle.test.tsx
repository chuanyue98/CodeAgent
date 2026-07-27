import type { ReactNode } from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, test, vi } from 'vitest';
import useResourceToggle from '../hooks/useResourceToggle';
import { ProjectProvider, useProject } from '../context/ProjectContext';

// Combines the hook under test with useProject() so the test can wait for
// ProjectContext's async /api/groups load to actually *commit* -- waiting
// only for fetch to have been called races the state update and would let
// toggleResources run against the still-empty initial groups state.
function useHarness() {
  const toggle = useResourceToggle();
  const { groups } = useProject();
  return { ...toggle, groups };
}

function jsonResponse(data: unknown) {
  return Promise.resolve({
    ok: true,
    status: 200,
    text: async () => JSON.stringify(data),
    json: async () => data,
  });
}

let postCalls: { url: string; body: Record<string, unknown> }[];

beforeEach(() => {
  postCalls = [];
  globalThis.fetch = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    const method = init?.method || 'GET';
    if (url === '/api/config') return jsonResponse({});
    if (url === '/api/projects') return jsonResponse([]);
    if (url === '/api/groups' && method === 'GET') {
      return jsonResponse({
        codeagent: { skills: ['a', 'b'], prompts: [], hooks: [], plugins: [] },
      });
    }
    if (url.startsWith('/api/groups/') && method === 'POST') {
      postCalls.push({ url, body: JSON.parse(init?.body as string) });
      return jsonResponse({ status: 'success' });
    }
    return Promise.reject(new Error(`Unhandled fetch to ${url}`));
  }) as unknown as typeof fetch;
});

function wrapper({ children }: { children: ReactNode }) {
  return <ProjectProvider>{children}</ProjectProvider>;
}

describe('useResourceToggle.toggleResources', () => {
  test('activating adds every id in one request, without duplicating existing ones', async () => {
    const { result } = renderHook(() => useHarness(), { wrapper });
    await waitFor(() => {
      expect(result.current.groups.codeagent?.skills).toEqual(['a', 'b']);
    });

    await act(async () => {
      await result.current.toggleResources('skills', ['b', 'c', 'd'], true);
    });

    expect(postCalls).toHaveLength(1);
    expect(postCalls[0].url).toBe('/api/groups/codeagent');
    expect((postCalls[0].body.skills as string[]).slice().sort()).toEqual(['a', 'b', 'c', 'd']);
  });

  test('deactivating removes only the given ids, in one request', async () => {
    const { result } = renderHook(() => useHarness(), { wrapper });
    await waitFor(() => {
      expect(result.current.groups.codeagent?.skills).toEqual(['a', 'b']);
    });

    await act(async () => {
      await result.current.toggleResources('skills', ['a'], false);
    });

    expect(postCalls).toHaveLength(1);
    expect(postCalls[0].body.skills).toEqual(['b']);
  });

  test('no-ops on an empty id list', async () => {
    const { result } = renderHook(() => useHarness(), { wrapper });
    await waitFor(() => {
      expect(result.current.groups.codeagent?.skills).toEqual(['a', 'b']);
    });

    await act(async () => {
      await result.current.toggleResources('skills', [], true);
    });

    expect(postCalls).toHaveLength(0);
  });
});
