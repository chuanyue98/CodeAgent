import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, test, vi } from 'vitest';
import { ProjectProvider, useProject } from '../context/ProjectContext';

const PROJECTS = [
  { path: '/work/demo', group: 'common', available: true },
  { path: '/work/other', group: 'web', available: true },
];

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
    if (url.includes('/api/projects')) return jsonResponse(PROJECTS);
    if (url.includes('/api/groups')) {
      return jsonResponse({ common: {}, web: {}, codeagent: {} });
    }
    return jsonResponse({});
  });
});

function Probe() {
  const { currentGroup, setCurrentGroup, refreshConfig } = useProject();
  return (
    <div>
      <span data-testid="group">{currentGroup}</span>
      <button onClick={() => setCurrentGroup('codeagent')}>pick codeagent</button>
      <button onClick={() => void refreshConfig()}>refresh</button>
    </div>
  );
}

describe('the header group follows the restored workspace', () => {
  test('a reload adopts the stored workspace\'s group', async () => {
    // Nothing "changes" the workspace on a reload -- it is restored -- so the
    // group used to stay at whatever the initial literal was, and the header
    // named a group the open project was not in.
    localStorage.setItem('codeagent.selectedWorkspace', '/work/other');

    render(
      <ProjectProvider>
        <Probe />
      </ProjectProvider>,
    );

    await waitFor(() => expect(screen.getByTestId('group').textContent).toBe('web'));
  });

  test('a group the user picked survives later refreshes', async () => {
    localStorage.setItem('codeagent.selectedWorkspace', '/work/demo');
    render(
      <ProjectProvider>
        <Probe />
      </ProjectProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('group').textContent).toBe('common'));

    screen.getByText('pick codeagent').click();
    await waitFor(() => expect(screen.getByTestId('group').textContent).toBe('codeagent'));

    screen.getByText('refresh').click();
    await new Promise(resolve => setTimeout(resolve, 50));
    expect(screen.getByTestId('group').textContent).toBe('codeagent');
  });
});
