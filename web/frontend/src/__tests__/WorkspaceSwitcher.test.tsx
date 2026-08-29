import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, test, vi } from 'vitest';
import WorkspaceSwitcher from '../components/WorkspaceSwitcher';
import { ProjectProvider, useProject } from '../context/ProjectContext';

function jsonResponse(data: unknown) {
  return Promise.resolve({
    ok: true,
    status: 200,
    text: async () => JSON.stringify(data),
    json: async () => data,
  });
}

function mockProjects(projects: unknown[]) {
  globalThis.fetch = vi.fn().mockImplementation((url: string) => {
    if (url.includes('/api/projects')) return jsonResponse(projects);
    return jsonResponse({});
  });
}

/** The selection is context state; this makes it assertable. */
function Selected() {
  const { selectedWorkspace } = useProject();
  return <output data-testid="selected">{selectedWorkspace}</output>;
}

function renderSwitcher() {
  return render(
    <MemoryRouter>
      <ProjectProvider>
        <WorkspaceSwitcher />
        <Selected />
      </ProjectProvider>
    </MemoryRouter>,
  );
}

function open() {
  fireEvent.click(screen.getByRole('button', { name: /current workspace/i }));
}

async function typePath(path: string) {
  fireEvent.change(screen.getByLabelText(/other directory/i), { target: { value: path } });
  fireEvent.click(screen.getByRole('button', { name: /use this directory/i }));
}

beforeEach(() => {
  localStorage.clear();
});

describe('WorkspaceSwitcher', () => {
  test('takes a directory the registry has never heard of', async () => {
    // The Local Terminal page used to own this case in a field of its own,
    // which meant two controls on one screen writing the same selection.
    mockProjects([{ path: '/workspace/proj', group: 'codeagent', available: true }]);
    renderSwitcher();
    await waitFor(() => expect(screen.getByTestId('selected').textContent).toBe('/workspace/proj'));

    open();
    await typePath('/somewhere/brand-new');

    expect(screen.getByTestId('selected').textContent).toBe('/somewhere/brand-new');
    // The heal-the-selection effect reads an unregistered path as "no longer
    // resolves"; without the custom-path list it bounces straight back to the
    // first registered project and the field is unusable.
    await waitFor(() =>
      expect(screen.getByTestId('selected').textContent).toBe('/somewhere/brand-new'),
    );
  });

  test('still works with nothing registered', async () => {
    // It used to render nothing at all in this case, which on a fresh install
    // left no way to point the app at a directory from anywhere in the UI.
    mockProjects([]);
    renderSwitcher();

    open();
    await typePath('/somewhere/brand-new');

    expect(screen.getByTestId('selected').textContent).toBe('/somewhere/brand-new');
  });

  test('offers a typed directory again next time', async () => {
    mockProjects([{ path: '/workspace/proj', group: 'codeagent', available: true }]);
    const first = renderSwitcher();
    await waitFor(() => expect(screen.getByTestId('selected').textContent).toBe('/workspace/proj'));
    open();
    await typePath('/somewhere/brand-new');
    first.unmount();

    renderSwitcher();
    open();
    expect(
      screen.getByRole('option', { name: /somewhere\/brand-new/ }),
    ).toBeTruthy();
  });
});
