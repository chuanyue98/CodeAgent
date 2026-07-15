import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import ConfigHub from '../components/ConfigHub';
import { ProjectProvider } from '../context/ProjectContext';
import { expect, test, describe } from 'vitest';

function renderConfigHub() {
  return render(
    <MemoryRouter>
      <ProjectProvider>
        <ConfigHub />
      </ProjectProvider>
    </MemoryRouter>
  );
}

describe('ConfigHub Component', () => {
  test('renders config data from context', async () => {
    renderConfigHub();

    // Wait until the selects appear (config loaded from context)
    const selects = await screen.findAllByRole('combobox', {}, { timeout: 3000 });
    // Global mock returns default_mode: 'local', language: 'en'
    expect(selects[0]).toHaveValue('local');
    expect(selects[1]).toHaveValue('en');
  });

  test('preserves editable row identity when an earlier project is removed', async () => {
    renderConfigHub();
    await screen.findAllByRole('combobox', {}, { timeout: 3000 });

    fireEvent.click(screen.getByRole('button', { name: 'Add Project' }));
    fireEvent.click(screen.getByRole('button', { name: 'Add Project' }));

    const firstProject = screen.getByLabelText('Project path 1');
    const secondProject = screen.getByLabelText('Project path 2');
    fireEvent.change(firstProject, { target: { value: '/workspace/first' } });
    fireEvent.change(secondProject, { target: { value: '/workspace/second' } });

    fireEvent.click(screen.getByRole('button', { name: 'Remove project /workspace/first' }));

    const remainingProject = screen.getByLabelText('Project path 1');
    expect(remainingProject).toBe(secondProject);
    expect(remainingProject).toHaveValue('/workspace/second');
  });

  test('blocks saving an empty project row', async () => {
    renderConfigHub();
    await screen.findAllByRole('combobox', {}, { timeout: 3000 });

    fireEvent.click(screen.getByRole('button', { name: 'Add Project' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save All Changes' }));

    expect(await screen.findByText(/Project path and resource group are required/)).toBeVisible();
  });
});
