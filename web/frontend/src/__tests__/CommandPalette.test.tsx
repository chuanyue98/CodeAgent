import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import CommandPalette from '../components/CommandPalette';
import { ProjectProvider } from '../context/ProjectContext';

function jsonResponse(data: unknown) {
  return Promise.resolve({
    ok: true,
    status: 200,
    text: async () => JSON.stringify(data),
    json: async () => data,
  });
}

beforeEach(() => {
  localStorage.clear();
  globalThis.fetch = vi.fn().mockImplementation((url: string) => {
    if (url.includes('/api/config')) return jsonResponse({});
    if (url.includes('/api/projects')) {
      return jsonResponse([{ path: '/workspace/proj-a', group: 'codeagent', available: true }]);
    }
    if (url.includes('/api/groups')) return jsonResponse({});
    if (url.includes('/api/analytics/sessions'))
    return jsonResponse({ sessions: [], nextCursor: null, total: 0 });
    if (url.endsWith('/api/tasks')) return jsonResponse([]);
    return Promise.reject(new Error(`Unhandled fetch to ${url}`));
  }) as unknown as typeof fetch;
});

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

function renderPalette() {
  return render(
    <MemoryRouter>
      <ProjectProvider>
        <CommandPalette />
      </ProjectProvider>
    </MemoryRouter>,
  );
}

describe('CommandPalette pinning', () => {
  test('pinning a workspace surfaces it in a Pinned section and persists to localStorage', async () => {
    renderPalette();
    fireEvent.click(screen.getByLabelText('Open command palette'));

    await screen.findByText('proj-a');
    fireEvent.click(screen.getByLabelText('Pin proj-a'));

    await waitFor(() => {
      expect(screen.getAllByText('proj-a')).toHaveLength(2);
    });
    expect(JSON.parse(localStorage.getItem('codeagent.pinnedPaletteItems') || '[]')).toContain(
      'workspace:/workspace/proj-a',
    );
  });

  test('unpinning removes the Pinned section clone', async () => {
    localStorage.setItem(
      'codeagent.pinnedPaletteItems',
      JSON.stringify(['workspace:/workspace/proj-a']),
    );
    renderPalette();
    fireEvent.click(screen.getByLabelText('Open command palette'));

    await waitFor(() => {
      expect(screen.getAllByText('proj-a')).toHaveLength(2);
    });

    fireEvent.click(screen.getAllByLabelText('Unpin proj-a')[0]);

    await waitFor(() => {
      expect(screen.getAllByText('proj-a')).toHaveLength(1);
    });
    expect(JSON.parse(localStorage.getItem('codeagent.pinnedPaletteItems') || '[]')).not.toContain(
      'workspace:/workspace/proj-a',
    );
  });
});
