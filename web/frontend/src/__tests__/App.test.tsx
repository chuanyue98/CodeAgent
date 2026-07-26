import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import App from '../App';
import { ProjectProvider } from '../context/ProjectContext';
import { expect, test, describe } from 'vitest';

function renderWithRouter(initialPath = '/skills') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <ProjectProvider>
        <App />
      </ProjectProvider>
    </MemoryRouter>
  );
}

describe('App Layout and Navigation', () => {
  test('renders the five workflow navigation links', async () => {
    renderWithRouter();
    await screen.findByRole('heading', { name: /Skills/i });
    expect(screen.getByRole('link', { name: 'Home' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Agent' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Automations' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Activity' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Settings' })).toBeInTheDocument();
  });

  test('shows correct page heading for /config route', async () => {
    renderWithRouter('/config');
    expect(await screen.findByRole('heading', { name: /Workspace/i })).toBeInTheDocument();
  });

  test('shows correct page heading for /dashboard route', async () => {
    renderWithRouter('/dashboard');
    expect(await screen.findByRole('heading', { name: /Tasks/i })).toBeInTheDocument();
  });
});
