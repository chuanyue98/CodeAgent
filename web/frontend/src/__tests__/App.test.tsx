import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
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
  test('renders navigation links', () => {
    renderWithRouter();
    // Nav links appear as <a> elements in the sidebar
    expect(screen.getByRole('link', { name: /Skills/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Prompts/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Configuration/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Dashboard/i })).toBeInTheDocument();
  });

  test('shows correct page heading for /config route', () => {
    renderWithRouter('/config');
    expect(screen.getByRole('heading', { name: /Configuration/i })).toBeInTheDocument();
  });

  test('shows correct page heading for /dashboard route', () => {
    renderWithRouter('/dashboard');
    expect(screen.getByRole('heading', { name: /Dashboard/i })).toBeInTheDocument();
  });
});
