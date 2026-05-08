import { render, screen } from '@testing-library/react';
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
});
