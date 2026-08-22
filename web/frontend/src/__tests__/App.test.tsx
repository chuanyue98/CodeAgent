import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import App from '../App';
import { ProjectProvider } from '../context/ProjectContext';
import { SystemMetricsProvider } from '../context/SystemMetricsContext';
import { expect, test, describe } from 'vitest';

function renderWithRouter(initialPath = '/skills') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <ProjectProvider>
        <SystemMetricsProvider>
          <App />
        </SystemMetricsProvider>
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

describe('Activity tabs are Sessions / Timeline / Usage', () => {
  test.each([
    ['/activity/sessions', 'Sessions'],
    ['/activity/timeline', 'Timeline'],
    ['/activity/usage', 'Usage'],
  ])('%s renders as %s', async (path, label) => {
    renderWithRouter(path);
    expect(await screen.findByRole('heading', { name: label })).toBeInTheDocument();
  });

  test.each([
    ['/activity/history', 'Sessions'],
    ['/activity/events', 'Timeline'],
    ['/activity/analytics', 'Usage'],
    ['/sessions', 'Sessions'],
    ['/audit', 'Timeline'],
    ['/analytics', 'Usage'],
  ])('the old %s location redirects to %s', async (path, label) => {
    renderWithRouter(path);
    expect(await screen.findByRole('heading', { name: label })).toBeInTheDocument();
  });

  test('a redirected deep link keeps its query string', async () => {
    // Dropping the query here would silently discard a saved filtered view,
    // or the params that open one session's detail.
    renderWithRouter('/activity/history?q=deploy&project=%2Fwork%2Fapp');
    await screen.findByRole('heading', { name: 'Sessions' });

    const tabs = screen.getByRole('navigation', { name: 'Activity sections' });
    const target = new URL(
      within(tabs).getByRole('link', { name: 'Timeline' }).getAttribute('href') ?? '',
      'http://localhost',
    );
    expect(target.searchParams.get('q')).toBe('deploy');
    expect(target.searchParams.get('project')).toBe('/work/app');
  });
});

describe('Logs lives under Automations', () => {
  test('renders at /automations/logs', async () => {
    renderWithRouter('/automations/logs');
    expect(await screen.findByRole('heading', { name: /^Logs$/ })).toBeInTheDocument();
  });

  test('appears as an Automations tab, not an Activity one', async () => {
    renderWithRouter('/automations/logs');
    await screen.findByRole('heading', { name: /^Logs$/ });

    const tabs = screen.getByRole('navigation', { name: 'Automations sections' });
    expect(within(tabs).getByRole('link', { name: 'Logs' })).toBeInTheDocument();
  });

  test('the old /activity/logs location redirects instead of 404ing', async () => {
    renderWithRouter('/activity/logs');
    expect(await screen.findByRole('heading', { name: /^Logs$/ })).toBeInTheDocument();
    expect(
      screen.getByRole('navigation', { name: 'Automations sections' }),
    ).toBeInTheDocument();
  });

  test('the legacy /logs shortcut still lands on the viewer', async () => {
    renderWithRouter('/logs');
    expect(await screen.findByRole('heading', { name: /^Logs$/ })).toBeInTheDocument();
  });
});
