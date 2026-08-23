import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import AuditTrail from '../components/AuditTrail';
import { ProjectProvider } from '../context/ProjectContext';
import type { AuditEvent } from '../api/audit';

function jsonResponse(data: unknown) {
  return Promise.resolve({
    ok: true,
    status: 200,
    text: async () => JSON.stringify(data),
    json: async () => data,
  });
}

const PROJECTS = [
  { path: '/workspace/project-a', group: 'common', available: true },
  { path: '/workspace/project-b', group: 'common', available: true },
];

function event(overrides: Partial<AuditEvent>): AuditEvent {
  return {
    event_id: 'evt-1',
    event_type: 'message',
    engine: 'claude',
    project_path: '/workspace/project-a',
    session_id: 'session-a',
    session_title: 'Session A',
    timestamp: '2026-08-21T10:00:00Z',
    role: 'user',
    model: 'claude-opus',
    content_preview: 'hello from claude',
    ...overrides,
  };
}

const BY_ENGINE: Record<string, AuditEvent[]> = {
  claude: [event({ event_id: 'claude-1', engine: 'claude', timestamp: '2026-08-21T10:00:00Z', content_preview: 'hello from claude' })],
  codex: [event({ event_id: 'codex-1', engine: 'codex', timestamp: '2026-08-21T12:00:00Z', content_preview: 'hello from codex' })],
  gemini: [event({ event_id: 'gemini-1', engine: 'gemini', timestamp: '2026-08-21T08:00:00Z', content_preview: 'hello from gemini' })],
  opencode: [event({ event_id: 'opencode-1', engine: 'opencode', timestamp: '2026-08-21T06:00:00Z', content_preview: 'hello from opencode' })],
};

let auditUrls: string[];
let failNext: boolean;

beforeEach(() => {
  auditUrls = [];
  failNext = false;
  globalThis.fetch = vi.fn().mockImplementation((url: string) => {
    if (url.includes('/api/config')) return jsonResponse({});
    if (url.includes('/api/projects')) return jsonResponse(PROJECTS);
    if (url.includes('/api/groups')) return jsonResponse({});
    if (url.includes('/api/history/audit')) {
      auditUrls.push(url);
      if (failNext) return Promise.reject(new Error('boom'));
      const engine = new URL(url, 'http://localhost').searchParams.get('engine');
      const events = engine ? (BY_ENGINE[engine] ?? []) : Object.values(BY_ENGINE).flat();
      const body = { events, count: events.length };
      return Promise.resolve({
        ok: true,
        status: 200,
        text: async () => JSON.stringify(body),
        json: async () => body,
      });
    }
    return Promise.reject(new Error(`Unhandled fetch to ${url}`));
  }) as unknown as typeof fetch;
});

afterEach(() => {
  vi.restoreAllMocks();
});

function renderAuditTrail(initialEntry = '/activity/timeline') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <ProjectProvider>
        <AuditTrail />
      </ProjectProvider>
    </MemoryRouter>,
  );
}

function auditParams(url: string) {
  return new URL(url, 'http://localhost').searchParams;
}

describe('AuditTrail engine filtering', () => {
  test('no engine selected fetches once, without an engine param', async () => {
    renderAuditTrail();
    await screen.findByText('4 条事件');

    expect(auditUrls).toHaveLength(1);
    expect(auditParams(auditUrls[0]).get('engine')).toBeNull();
  });

  test('selecting several engines issues one request per engine', async () => {
    renderAuditTrail();
    await screen.findByText('4 条事件');
    auditUrls.length = 0;

    fireEvent.click(screen.getByRole('button', { name: 'claude' }));
    await screen.findByText('1 条事件');

    fireEvent.click(screen.getByRole('button', { name: 'codex' }));
    await screen.findByText('2 条事件');

    // One request per selected engine — the previous implementation fetched
    // unfiltered and narrowed client-side, so events from deselected engines
    // consumed the response window and matching ones were silently dropped.
    const engines = auditUrls.map(url => auditParams(url).get('engine'));
    expect(engines).toContain('claude');
    expect(engines).toContain('codex');
    expect(engines).not.toContain(null);
  });

  test('merged multi-engine results stay in newest-first order', async () => {
    renderAuditTrail();
    await screen.findByText('4 条事件');

    fireEvent.click(screen.getByRole('button', { name: 'claude' }));
    await screen.findByText('1 条事件');
    fireEvent.click(screen.getByRole('button', { name: 'codex' }));
    await screen.findByText('2 条事件');

    const rendered = screen.getAllByText(/^user: hello from /).map(node => node.textContent);
    // codex is 12:00Z, claude is 10:00Z
    expect(rendered[0]).toContain('codex');
    expect(rendered[1]).toContain('claude');
  });
});

describe('AuditTrail date range', () => {
  test('sends the instants the local calendar day actually spans', async () => {
    renderAuditTrail();
    await screen.findByText('4 条事件');
    auditUrls.length = 0;

    fireEvent.change(screen.getByLabelText('日期范围起点'), { target: { value: '2026-08-21' } });

    await waitFor(() => expect(auditUrls).toHaveLength(1));
    const since = auditParams(auditUrls[0]).get('since')!;
    expect(new Date(since).getHours()).toBe(0);
    expect(new Date(since).getDate()).toBe(21);

    fireEvent.change(screen.getByLabelText('日期范围终点'), { target: { value: '2026-08-21' } });

    await waitFor(() => expect(auditUrls.length).toBeGreaterThan(1));
    const until = auditParams(auditUrls.at(-1)!).get('until')!;
    expect(new Date(until).getHours()).toBe(23);
    expect(new Date(until).getDate()).toBe(21);
  });
});

describe('AuditTrail project filter', () => {
  test('sends the project param when one is pinned in the URL', async () => {
    renderAuditTrail('/activity/timeline?project=%2Fworkspace%2Fproject-a');
    await screen.findByText('4 条事件');

    expect(auditParams(auditUrls[0]).get('project')).toBe('/workspace/project-a');
  });

  test('omits the project param for the all-projects choice', async () => {
    renderAuditTrail('/activity/timeline?project=all');
    await screen.findByText('4 条事件');

    expect(auditParams(auditUrls[0]).get('project')).toBeNull();
  });

  test('reads search, dates and engines back out of the URL', async () => {
    renderAuditTrail('/activity/timeline?q=codex&engines=codex&from=2026-08-21');
    await screen.findByText('1 条事件');

    expect(screen.getByPlaceholderText('项目、会话、内容…')).toHaveValue('codex');
    expect(screen.getByRole('button', { name: 'codex', pressed: true })).toBeVisible();
    expect(auditParams(auditUrls[0]).get('engine')).toBe('codex');
  });

  test('a session deep link does not hijack the list project filter', async () => {
    // sessionProject points somewhere other than the workspace: it must open
    // the drawer without becoming the filter the list is fetched with.
    renderAuditTrail(
      '/activity/timeline?session=session-a&sessionEngine=claude&sessionProject=%2Felsewhere%2Fproject-z',
    );
    await screen.findByText('4 条事件');

    expect(auditParams(auditUrls[0]).get('project')).toBe('/workspace/project-a');
  });

  test('follows the workspace when no project is pinned', async () => {
    renderAuditTrail();
    await screen.findByText('4 条事件');

    // ProjectProvider auto-selects the first valid workspace, and Activity
    // now follows it like the rest of the app rather than ignoring it.
    expect(auditParams(auditUrls[0]).get('project')).toBe('/workspace/project-a');
  });

  test('issues exactly one request while the workspace resolves', async () => {
    renderAuditTrail();
    await screen.findByText('4 条事件');

    expect(auditUrls).toHaveLength(1);
  });
});

describe('AuditTrail error handling', () => {
  test('a failed load offers a retry that refetches', async () => {
    failNext = true;
    renderAuditTrail();

    await screen.findByText('加载事件失败');
    failNext = false;

    fireEvent.click(screen.getByRole('button', { name: '重试' }));

    await screen.findByText('4 条事件');
  });
});
