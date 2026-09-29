import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { QueryClientProvider } from '@tanstack/react-query';
import App from '../App';
import { ProjectProvider } from '../context/ProjectContext';
import { SystemMetricsProvider } from '../context/SystemMetricsContext';
import { LanguageProvider } from '../i18n/LanguageProvider';
import { createQueryClient } from '../utils/queryClient';
import { afterEach, expect, test, describe, vi } from 'vitest';

afterEach(() => {
  vi.unstubAllGlobals();
});

/**
 * The tab carrying aria-current is what identifies the leaf route. The page
 * heading names the *section* (Agent, Activity, Settings), so it can no
 * longer stand in for "did this URL resolve to the right page".
 */
function activeTab(name: string | RegExp) {
  return screen.findByRole('link', { name, current: 'page' });
}

function renderWithRouter(initialPath = '/skills') {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[initialPath]}>
        <ProjectProvider>
          <LanguageProvider>
            <SystemMetricsProvider>
              <App />
            </SystemMetricsProvider>
          </LanguageProvider>
        </ProjectProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('App Layout and Navigation', () => {
  test('renders the six navigation links', async () => {
    renderWithRouter();
    await activeTab(/Resources/i);
    // The desktop rail and the phone's bottom bar are both in the DOM (CSS
    // shows one), so each destination appears once per bar.
    for (const name of ['Overview', 'Sessions', 'History', 'Automations', 'Extensions', 'Settings']) {
      expect(screen.getAllByRole('link', { name }).length).toBeGreaterThan(0);
    }
  });

  test('the heading names the section, not the tab below it', async () => {
    // Both used to read "Sessions", one directly above the other.
    renderWithRouter('/activity/sessions');
    expect(await activeTab('Sessions')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('History');
  });

  test('/config lands on Settings', async () => {
    renderWithRouter('/config');
    expect(await screen.findByRole('link', { name: 'Settings', current: 'page' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Settings');
  });

  test('shows correct page heading for /dashboard route', async () => {
    renderWithRouter('/dashboard');
    expect(await activeTab(/Tasks/i)).toBeInTheDocument();
  });
});

describe('Activity tabs are Sessions / Usage', () => {
  test.each([
    ['/activity/sessions', 'Sessions'],
    ['/activity/usage', 'Usage'],
  ])('%s renders as %s', async (path, label) => {
    renderWithRouter(path);
    expect(await activeTab(label)).toBeInTheDocument();
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
    expect(await activeTab(label)).toBeInTheDocument();
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

    await activeTab(/Resources/i);
    const tabs = screen.getByRole('navigation', { name: 'Extensions sections' });
    expect(within(tabs).getByRole('link', { name: 'Resources' })).toBeInTheDocument();
  });

  test('a redirected deep link keeps its query string', async () => {
    // Dropping the query here would silently discard a saved filtered view,
    // or the params that open one session's detail.
    renderWithRouter('/activity/history?q=deploy&project=%2Fwork%2Fapp');
    await activeTab('Sessions');

    const tabs = screen.getByRole('navigation', { name: 'History sections' });
    const target = new URL(
      within(tabs).getByRole('link', { name: 'Usage' }).getAttribute('href') ?? '',
      'http://localhost',
    );
    expect(target.searchParams.get('q')).toBe('deploy');
    expect(target.searchParams.get('project')).toBe('/work/app');
  });
});

describe('Extensions holds Resources and MCP', () => {
  test.each([
    ['/extensions/resources', /^Resources$/],
    ['/extensions/mcp', /^MCP$/],
    ['/settings/resources', /^Resources$/],
    ['/settings/mcp', /^MCP$/],
    ['/mcp', /^MCP$/],
  ])('%s opens the %s tab', async (path, label) => {
    renderWithRouter(path);
    expect(await activeTab(label)).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Extensions sections' })).toBeInTheDocument();
  });

  test('Settings is one page: no tab row, system health is a section of it', async () => {
    renderWithRouter('/settings/workspace');
    expect(await screen.findByRole('link', { name: 'Settings', current: 'page' })).toBeInTheDocument();
    expect(screen.queryByRole('navigation', { name: 'Settings sections' })).toBeNull();
    const sections = await screen.findByRole('navigation', { name: 'Settings' });
    expect(within(sections).getByRole('button', { name: /System health/ })).toBeInTheDocument();
  });

  test.each(['/settings/system', '/system'])('the old %s address opens the System health section', async path => {
    // The section loads its own health report; without an answer it shows an
    // error instead of its heading.
    const otherwise = globalThis.fetch;
    vi.stubGlobal('fetch', (url: RequestInfo | URL, init?: RequestInit) =>
      String(url).includes('/api/system/health')
        ? Promise.resolve(new Response(JSON.stringify({ status: 'ok', sections: [] }), { status: 200 }))
        : otherwise(url, init),
    );
    renderWithRouter(path);
    const sections = await screen.findByRole('navigation', { name: 'Settings' });
    // The section's own content, not just its rail entry, proves it is the one open.
    expect(await screen.findByRole('heading', { name: /System health/i, level: 2 })).toBeInTheDocument();
    expect(within(sections).getByRole('button', { name: /System health/ })).toBeInTheDocument();
  });
});

describe('Logs lives under Automations', () => {
  test('renders at /automations/logs', async () => {
    renderWithRouter('/automations/logs');
    expect(await activeTab(/^Logs$/)).toBeInTheDocument();
  });

  test('appears as an Automations tab, not an Activity one', async () => {
    renderWithRouter('/automations/logs');
    await activeTab(/^Logs$/);

    const tabs = screen.getByRole('navigation', { name: 'Automations sections' });
    expect(within(tabs).getByRole('link', { name: 'Logs' })).toBeInTheDocument();
  });

  test('the old /activity/logs location redirects instead of 404ing', async () => {
    renderWithRouter('/activity/logs');
    expect(await activeTab(/^Logs$/)).toBeInTheDocument();
    expect(
      screen.getByRole('navigation', { name: 'Automations sections' }),
    ).toBeInTheDocument();
  });

  test('the legacy /logs shortcut still lands on the viewer', async () => {
    renderWithRouter('/logs');
    expect(await activeTab(/^Logs$/)).toBeInTheDocument();
  });
});
