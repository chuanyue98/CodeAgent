import { act, render, waitFor } from '@testing-library/react';
import { expect, test, describe, vi, beforeEach } from 'vitest';
import { ProjectProvider, useProject } from '../context/ProjectContext';

function Probe({ onReady }: { onReady: (api: ReturnType<typeof useProject>) => void }) {
  const api = useProject();
  onReady(api);
  return null;
}

describe('ProjectContext', () => {
  beforeEach(() => {
    vi.mocked(globalThis.fetch).mockClear();
  });

  test('switching groups does not refetch config -- refreshConfig only runs once, on mount', async () => {
    let latest: ReturnType<typeof useProject> | null = null;
    render(
      <ProjectProvider>
        <Probe onReady={api => { latest = api; }} />
      </ProjectProvider>,
    );

    await waitFor(() => expect(latest?.config).not.toBeNull());

    const configCallsAfterMount = vi
      .mocked(globalThis.fetch)
      .mock.calls.filter(([url]) => String(url).includes('/api/config')).length;
    expect(configCallsAfterMount).toBe(1);

    act(() => {
      latest?.setCurrentGroup('common');
    });
    act(() => {
      latest?.setCurrentGroup('work');
    });
    act(() => {
      latest?.setCurrentGroup('codeagent');
    });

    const configCallsAfterSwitching = vi
      .mocked(globalThis.fetch)
      .mock.calls.filter(([url]) => String(url).includes('/api/config')).length;
    expect(configCallsAfterSwitching).toBe(1);
  });
});
