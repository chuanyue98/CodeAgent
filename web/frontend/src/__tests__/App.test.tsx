import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import App from '../App';
import { ProjectProvider } from '../context/ProjectContext';
import { SystemMetricsProvider } from '../context/SystemMetricsContext';
import { LanguageProvider } from '../i18n/LanguageProvider';
import { expect, test, describe } from 'vitest';

function renderWithRouter(initialPath = '/skills') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <ProjectProvider>
        <LanguageProvider>
          <SystemMetricsProvider>
            <App />
          </SystemMetricsProvider>
        </LanguageProvider>
      </ProjectProvider>
    </MemoryRouter>
  );
}

describe('App Layout and Navigation', () => {
  test('renders the five workflow navigation links', async () => {
    renderWithRouter();
    await screen.findByRole('heading', { name: /Resources/i });
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

describe('Activity tabs are Sessions / Usage', () => {
  test.each([
    ['/activity/sessions', 'Sessions'],
    ['/activity/usage', 'Usage'],
  ])('%s renders as %s', async (path, label) => {
    renderWithRouter(path);
    expect(await screen.findByRole('heading', { name: label })).toBeInTheDocument();
  });

  // Timeline is gone; every URL that used to point at it now lands on
  // Sessions, which understands the same single-session deep-link params.
  test.each([
    ['/activity/history', 'Sessions'],
    ['/activity/timeline', 'Sessions'],
    ['/activity/events', 'Sessions'],
    ['/activity/analytics', 'Usage'],
    ['/sessions', 'Sessions'],
    ['/audit', 'Sessions'],
    ['/analytics', 'Usage'],
  ])('the old %s location redirects to %s', async (path, label) => {
    renderWithRouter(path);
    expect(await screen.findByRole('heading', { name: label })).toBeInTheDocument();
  });

  // Skills/Prompts/Hooks/Plugins are one page now, so every address that
  // named one of them has to still resolve. That the destination opens on the
  // *right kind* is asserted in ResourceHub's own test, where the resource
  // data can be mocked; here the question is only whether the route survives.
  test.each([
    '/skills',
    '/prompts',
    '/hooks',
    '/plugins',
    '/settings/skills',
    '/settings/plugins',
    '/settings/capabilities',
    '/settings/capabilities/hooks',
  ])('the old %s location still resolves to Resources', async path => {
    renderWithRouter(path);

    await screen.findByRole('heading', { name: /Resources/i });
    const tabs = screen.getByRole('navigation', { name: 'Settings sections' });
    expect(within(tabs).getByRole('link', { name: 'Resources' })).toBeInTheDocument();
  });

  test('a redirected deep link keeps its query string', async () => {
    // Dropping the query here would silently discard a saved filtered view,
    // or the params that open one session's detail.
    renderWithRouter('/activity/history?q=deploy&project=%2Fwork%2Fapp');
    await screen.findByRole('heading', { name: 'Sessions' });

    const tabs = screen.getByRole('navigation', { name: 'Activity sections' });
    const target = new URL(
      within(tabs).getByRole('link', { name: 'Usage' }).getAttribute('href') ?? '',
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
