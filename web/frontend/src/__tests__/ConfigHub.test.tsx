import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import ConfigHub from '../components/ConfigHub';
import { ProjectProvider } from '../context/ProjectContext';
import { LanguageProvider } from '../i18n/LanguageProvider';
import { expect, test, describe, vi, beforeEach } from 'vitest';

const mockNavigate = vi.fn();
vi.mock('react-router', async () => {
  const actual = await vi.importActual<typeof import('react-router')>('react-router');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

// The page owns the language setting now, and useLanguage — unlike useT —
// has no provider-less fallback.
function renderConfigHub() {
  return render(
    <MemoryRouter>
      <ProjectProvider>
        <LanguageProvider initialLanguage="en">
          <ConfigHub />
        </LanguageProvider>
      </ProjectProvider>
    </MemoryRouter>
  );
}

describe('ConfigHub Component', () => {
  beforeEach(() => {
    mockNavigate.mockClear();
  });

  test('renders config data from context', async () => {
    renderConfigHub();

    await screen.findByText(/CodeAgent runs locally/);
  });

  test('preserves editable row identity when an earlier project is removed', async () => {
    renderConfigHub();
    await screen.findByText(/CodeAgent runs locally/, {}, { timeout: 3000 });

    fireEvent.click(screen.getByRole('button', { name: 'Add Workspace' }));
    fireEvent.click(screen.getByRole('button', { name: 'Add Workspace' }));

    const firstProject = screen.getByLabelText('Workspace path 1');
    const secondProject = screen.getByLabelText('Workspace path 2');
    fireEvent.change(firstProject, { target: { value: '/workspace/first' } });
    fireEvent.change(secondProject, { target: { value: '/workspace/second' } });

    fireEvent.click(screen.getByRole('button', { name: 'Remove workspace /workspace/first' }));

    const remainingProject = screen.getByLabelText('Workspace path 1');
    expect(remainingProject).toBe(secondProject);
    expect(remainingProject).toHaveValue('/workspace/second');
  });

  test('blocks saving an empty project row', async () => {
    renderConfigHub();
    await screen.findByText(/CodeAgent runs locally/, {}, { timeout: 3000 });

    fireEvent.click(screen.getByRole('button', { name: 'Add Workspace' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save All Changes' }));

    expect(await screen.findByText(/Workspace path and resource group are required/)).toBeVisible();
  });

  test('renders workspace input with Folder icon and availability indicators', async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/projects')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: async () => JSON.stringify([
            { path: '/workspace/valid', group: 'codeagent', available: true },
            { path: '/workspace/missing', group: 'common', available: false },
          ]),
          json: async () => [
            { path: '/workspace/valid', group: 'codeagent', available: true },
            { path: '/workspace/missing', group: 'common', available: false },
          ],
        });
      }
      return originalFetch(url);
    });

    try {
      renderConfigHub();
      const validPathInput = await screen.findByDisplayValue('/workspace/valid');
      const missingPathInput = screen.getByDisplayValue('/workspace/missing');

      // Verify folder icons exist
      const folderIcons = screen.getAllByTestId('workspace-folder-icon');
      expect(folderIcons.length).toBe(2);

      // Verify available indicator (CheckCircle2)
      expect(screen.getByTestId('workspace-status-available')).toBeVisible();

      // Verify missing indicator (AlertTriangle) and missing notice
      expect(screen.getByTestId('workspace-status-missing')).toBeVisible();
      expect(screen.getByText(/This path was not found on disk/)).toBeVisible();

      // Check input attributes and wrapper classes
      expect(validPathInput).toHaveAttribute('type', 'text');
      expect(validPathInput).toHaveAttribute('placeholder', '/absolute/path/to/your/project');
      const missingContainer = missingPathInput.closest('.border-amber-300');
      expect(missingContainer).not.toBeNull();
      expect(missingContainer?.className).toContain('bg-amber-50/20');
      expect(missingContainer?.className).toContain('focus-within:ring-2');
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  test('renders View Resources buttons and navigates to group resource settings on click', async () => {
    renderConfigHub();
    await screen.findByText(/CodeAgent runs locally/, {}, { timeout: 3000 });

    // Switch to groups tab
    fireEvent.click(screen.getByRole('button', { name: /Resource Groups/i }));

    const viewButtons = screen.getAllByRole('button', { name: /View Resources/i });
    expect(viewButtons.length).toBeGreaterThanOrEqual(1);

    // Click the View Resources button for the first group (codeagent)
    fireEvent.click(viewButtons[0]);

    expect(mockNavigate).toHaveBeenCalledWith('/extensions/resources?group=codeagent');
  });

  test('switches between configuration sections via sidebar navigation', async () => {
    renderConfigHub();
    await screen.findByText(/CodeAgent runs locally/, {}, { timeout: 3000 });

    // Initially in workspaces tab
    expect(screen.getByRole('button', { name: 'Add Workspace' })).toBeVisible();

    // Click Proxy tab
    fireEvent.click(screen.getByRole('button', { name: /Network Proxy/i }));
    expect(screen.getByRole('button', { name: /Add Gateway/i })).toBeVisible();

    // Click General tab
    fireEvent.click(screen.getByRole('button', { name: /General & Language/i }));
    expect(screen.getByLabelText(/Private Resource Root/i)).toBeVisible();

    // Click Workspaces tab again
    fireEvent.click(screen.getByRole('button', { name: /^Workspaces/i }));
    expect(screen.getByRole('button', { name: 'Add Workspace' })).toBeVisible();
  });

  test('editing and reverting an input clears dirty state without locking form', async () => {
    renderConfigHub();
    await screen.findByText(/CodeAgent runs locally/, {}, { timeout: 3000 });

    fireEvent.click(screen.getByRole('button', { name: /General & Language/i }));
    const input = screen.getByLabelText(/Private Resource Root/i);
    expect(screen.getByRole('button', { name: /Save All Changes/i })).toBeDisabled();

    fireEvent.change(input, { target: { value: '/custom/resource/root' } });
    expect(screen.getByRole('button', { name: /Save All Changes/i })).not.toBeDisabled();
    expect(screen.getByRole('button', { name: /Discard/i })).toBeVisible();

    // Revert the edit
    fireEvent.change(input, { target: { value: '' } });
    expect(screen.getByRole('button', { name: /Save All Changes/i })).toBeDisabled();
  });

  test('saving project path with surrounding whitespace normalizes and resets dirty state', async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn().mockImplementation((url: string, options?: RequestInit) => {
      if (url.includes('/api/config')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: async () => JSON.stringify({ project_registry: [{ path: '/workspace/trimmed', group: 'common' }] }),
          json: async () => ({ project_registry: [{ path: '/workspace/trimmed', group: 'common' }] }),
        });
      }
      if (url.includes('/api/projects')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: async () => JSON.stringify([{ path: '/workspace/trimmed', group: 'common', available: true }]),
          json: async () => [{ path: '/workspace/trimmed', group: 'common', available: true }],
        });
      }
      if (url.includes('/api/groups')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          text: async () => JSON.stringify({ common: { skills: [], prompts: [], hooks: [], plugins: [] } }),
          json: async () => ({ common: { skills: [], prompts: [], hooks: [], plugins: [] } }),
        });
      }
      return originalFetch(url, options);
    });

    try {
      renderConfigHub();
      await screen.findByText(/CodeAgent runs locally/, {}, { timeout: 3000 });

      const projectInput = screen.getByLabelText('Workspace path 1');
      fireEvent.change(projectInput, { target: { value: '  /workspace/trimmed  ' } });

      const saveBtn = screen.getByRole('button', { name: /Save All Changes/i });
      expect(saveBtn).not.toBeDisabled();

      fireEvent.click(saveBtn);
      await screen.findByText(/Saved to config\.json/);
      expect(screen.getByRole('button', { name: /Save All Changes/i })).toBeDisabled();
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
