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

    const viewButtons = screen.getAllByRole('button', { name: /View Resources/i });
    expect(viewButtons.length).toBeGreaterThanOrEqual(1);

    // Click the View Resources button for the first group (codeagent)
    fireEvent.click(viewButtons[0]);

    expect(mockNavigate).toHaveBeenCalledWith('/settings/resources?group=codeagent');
  });
});
