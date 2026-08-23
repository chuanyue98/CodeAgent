import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
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
});
