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
    await screen.findByRole('heading', { name: /技能/i });
    expect(screen.getByRole('link', { name: '首页' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Agent' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '自动化' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '动态' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '设置' })).toBeInTheDocument();
  });

  test('shows correct page heading for /config route', async () => {
    renderWithRouter('/config');
    expect(await screen.findByRole('heading', { name: /工作区/i })).toBeInTheDocument();
  });

  test('shows correct page heading for /dashboard route', async () => {
    renderWithRouter('/dashboard');
    expect(await screen.findByRole('heading', { name: /任务/i })).toBeInTheDocument();
  });
});

describe('Activity tabs are 会话 / 时间线 / 用量', () => {
  test.each([
    ['/activity/sessions', '会话'],
    ['/activity/timeline', '时间线'],
    ['/activity/usage', '用量'],
  ])('%s renders as %s', async (path, label) => {
    renderWithRouter(path);
    expect(await screen.findByRole('heading', { name: label })).toBeInTheDocument();
  });

  test.each([
    ['/activity/history', '会话'],
    ['/activity/events', '时间线'],
    ['/activity/analytics', '用量'],
    ['/sessions', '会话'],
    ['/audit', '时间线'],
    ['/analytics', '用量'],
  ])('the old %s location redirects to %s', async (path, label) => {
    renderWithRouter(path);
    expect(await screen.findByRole('heading', { name: label })).toBeInTheDocument();
  });

  test('a redirected deep link keeps its query string', async () => {
    // Dropping the query here would silently discard a saved filtered view,
    // or the params that open one session's detail.
    renderWithRouter('/activity/history?q=deploy&project=%2Fwork%2Fapp');
    await screen.findByRole('heading', { name: '会话' });

    const tabs = screen.getByRole('navigation', { name: '动态分区' });
    const target = new URL(
      within(tabs).getByRole('link', { name: '时间线' }).getAttribute('href') ?? '',
      'http://localhost',
    );
    expect(target.searchParams.get('q')).toBe('deploy');
    expect(target.searchParams.get('project')).toBe('/work/app');
  });
});

describe('Logs lives under Automations', () => {
  test('renders at /automations/logs', async () => {
    renderWithRouter('/automations/logs');
    expect(await screen.findByRole('heading', { name: /^日志$/ })).toBeInTheDocument();
  });

  test('appears as an Automations tab, not an Activity one', async () => {
    renderWithRouter('/automations/logs');
    await screen.findByRole('heading', { name: /^日志$/ });

    const tabs = screen.getByRole('navigation', { name: '自动化分区' });
    expect(within(tabs).getByRole('link', { name: '日志' })).toBeInTheDocument();
  });

  test('the old /activity/logs location redirects instead of 404ing', async () => {
    renderWithRouter('/activity/logs');
    expect(await screen.findByRole('heading', { name: /^日志$/ })).toBeInTheDocument();
    expect(
      screen.getByRole('navigation', { name: '自动化分区' }),
    ).toBeInTheDocument();
  });

  test('the legacy /logs shortcut still lands on the viewer', async () => {
    renderWithRouter('/logs');
    expect(await screen.findByRole('heading', { name: /^日志$/ })).toBeInTheDocument();
  });
});
