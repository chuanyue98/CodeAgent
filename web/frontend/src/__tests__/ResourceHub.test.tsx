import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, test, vi } from 'vitest';
import ResourceHub from '../components/ResourceHub';
import { ProjectProvider } from '../context/ProjectContext';

function jsonResponse(data: unknown) {
  return Promise.resolve({
    ok: true,
    status: 200,
    text: async () => JSON.stringify(data),
    json: async () => data,
  });
}

const SKILLS = {
  dev: [
    { id: 'dev/code-review', name: 'code-review', description: 'Structured diff review', readme: '# Review' },
    { id: 'dev/lint-fix', name: 'lint-fix', description: 'Repair lint failures', readme: '# Lint' },
  ],
  ops: [{ id: 'ops/deploy', name: 'deploy', description: 'Ship a release', readme: '# Deploy' }],
};

const PLUGINS = {
  base: [{ id: 'base/uv-runner', name: 'uv-runner', description: 'Run through uv', readme: '# uv' }],
};

const HOOKS = [
  {
    id: 'base/lint-on-save',
    name: 'lint-on-save',
    event: 'PostToolUse',
    description: 'Runs the linter after an edit',
    path: '/hooks/lint.sh',
  },
];

const PROMPTS = [
  {
    id: 'base',
    name: 'base',
    description: 'Baseline prompt group',
    readme: '# Base',
    files: [{ name: 'style.md', path: '/prompt/base/style.md' }],
  },
];

const ENGINE_MOUNTS = [
  { id: 'claude', name: 'Claude Code', mounts: ['skills', 'hooks', 'plugins'] },
  { id: 'opencode', name: 'OpenCode', mounts: ['skills', 'hooks', 'plugins'] },
  { id: 'codex', name: 'Codex', mounts: ['skills', 'hooks', 'plugins'] },
  { id: 'codebuddy', name: 'CodeBuddy', mounts: ['skills', 'plugins'] },
  { id: 'antigravity', name: 'Antigravity', mounts: ['skills'] },
];

let failing: Set<string>;
let engineMountsFail: boolean;

beforeEach(() => {
  failing = new Set();
  engineMountsFail = false;
  globalThis.fetch = vi.fn().mockImplementation((url: string) => {
    if (url.includes('/api/system/engines')) {
      return engineMountsFail
        ? Promise.reject(new Error('down'))
        : jsonResponse({ engines: ENGINE_MOUNTS });
    }
    if (url.includes('/api/config')) {
      return jsonResponse({ groups: { codeagent: { skills: ['dev/code-review'], prompts: [], hooks: [], plugins: [] } } });
    }
    if (url.includes('/api/projects')) return jsonResponse([]);
    if (url.includes('/api/groups')) {
      return jsonResponse({ codeagent: { skills: ['dev/code-review'], prompts: [], hooks: [], plugins: [] } });
    }
    for (const [fragment, body] of [
      ['/api/skills', SKILLS],
      ['/api/plugins', PLUGINS],
      ['/api/hooks', HOOKS],
      ['/api/prompts', PROMPTS],
    ] as const) {
      if (url.includes(fragment)) {
        if (failing.has(fragment)) {
          return Promise.resolve({
            ok: false,
            status: 500,
            text: async () => JSON.stringify({ detail: 'boom' }),
            json: async () => ({ detail: 'boom' }),
          });
        }
        return jsonResponse(body);
      }
    }
    return Promise.reject(new Error(`Unhandled fetch to ${url}`));
  }) as unknown as typeof fetch;
});

function renderHub(path = '/settings/resources') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <ProjectProvider>
        <ResourceHub />
      </ProjectProvider>
    </MemoryRouter>,
  );
}

describe('ResourceHub sidebar', () => {
  test('lists every kind with its categories nested underneath', async () => {
    renderHub();

    expect(await screen.findByRole('button', { name: /Skills/ })).toBeInTheDocument();
    for (const kind of ['Prompts', 'Hooks', 'Plugins']) {
      expect(screen.getByRole('button', { name: new RegExp(kind) })).toBeInTheDocument();
    }
    // Categories are the second level, not a flat list of kinds.
    expect(screen.getByRole('button', { name: /dev/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /ops/ })).toBeInTheDocument();
  });

  test('collapsing a kind hides its categories', async () => {
    renderHub();
    const skills = await screen.findByRole('button', { name: /Skills/ });

    expect(skills).toHaveAttribute('aria-expanded', 'true');
    fireEvent.click(skills);

    expect(skills).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('button', { name: /dev/ })).not.toBeInTheDocument();
  });
});

describe('ResourceHub engine marks', () => {
  /** The row (role=button) whose heading is `name`. */
  async function rowFor(name: string): Promise<HTMLElement> {
    const heading = await screen.findByRole('heading', { level: 2, name });
    return heading.closest('[role="button"]') as HTMLElement;
  }

  test('a skill is marked as attached to every engine', async () => {
    renderHub();
    const row = await rowFor('code-review');

    const marks = await within(row).findByRole('img', { name: /Attached to/ });
    for (const engine of ['Claude', 'OpenCode', 'Codex', 'CodeBuddy', 'Antigravity']) {
      expect(marks.getAttribute('aria-label')).toContain(engine);
    }
  });

  test('a hook is marked only for the engines whose launcher attaches hooks', async () => {
    renderHub();
    await screen.findByText('code-review');
    fireEvent.change(screen.getByLabelText('Search all resources'), { target: { value: 'lint-on' } });

    const marks = await within(await rowFor('lint-on-save')).findByRole('img', { name: /Attached to/ });
    const label = marks.getAttribute('aria-label') ?? '';
    expect(label).toContain('Claude');
    expect(label).toContain('Codex');
    expect(label).not.toContain('CodeBuddy');
    expect(label).not.toContain('Antigravity');
  });

  test('a plugin skips Antigravity, which does not take the group\'s plugins', async () => {
    renderHub();
    await screen.findByText('code-review');
    fireEvent.change(screen.getByLabelText('Search all resources'), { target: { value: 'uv-runner' } });

    const marks = await within(await rowFor('uv-runner')).findByRole('img', { name: /Attached to/ });
    expect(marks.getAttribute('aria-label')).toContain('CodeBuddy');
    expect(marks.getAttribute('aria-label')).not.toContain('Antigravity');
  });

  test('a hollow dot names the engine that does not take the kind', async () => {
    renderHub();
    await screen.findByText('code-review');
    fireEvent.change(screen.getByLabelText('Search all resources'), { target: { value: 'lint-on' } });

    const row = await rowFor('lint-on-save');
    await within(row).findByRole('img', { name: /Attached to/ });
    expect(row.querySelector('[title="Antigravity does not take this kind"]')).not.toBeNull();
  });

  test('prompts carry no marks, since no launcher attaches them per engine', async () => {
    renderHub();
    await screen.findByText('code-review');
    fireEvent.change(screen.getByLabelText('Search all resources'), { target: { value: 'baseline' } });

    const row = await rowFor('base');
    expect(within(row).queryByRole('img')).toBeNull();
  });

  test('when the table cannot be loaded, rows show no marks rather than claim none attach', async () => {
    engineMountsFail = true;
    renderHub();
    const row = await rowFor('code-review');

    await new Promise(resolve => setTimeout(resolve, 50));
    expect(within(row).queryByRole('img')).toBeNull();
  });
});

describe('ResourceHub search', () => {
  // The reason the four tabs became one page: each tab's search only ever
  // searched its own kind, so "was that lint thing a skill or a hook?" had no
  // answer anywhere in the app.
  test('one search box matches across every kind at once', async () => {
    renderHub();
    await screen.findByText('code-review');

    fireEvent.change(screen.getByLabelText('Search all resources'), {
      target: { value: 'lint' },
    });

    await waitFor(() => expect(screen.getByText('lint-fix')).toBeVisible());
    expect(screen.getByText('lint-on-save')).toBeVisible();
    expect(screen.getByText('2 matches across all kinds')).toBeVisible();
  });

  test('a hit says which kind it came from', async () => {
    renderHub();
    await screen.findByText('code-review');

    fireEvent.change(screen.getByLabelText('Search all resources'), {
      target: { value: 'lint' },
    });

    const hit = (await screen.findByText('lint-on-save')).closest('[role="button"]');
    // Without the badge, a mixed result list is a set of names with no clue
    // which of the four things each one is.
    expect(within(hit as HTMLElement).getByText('Hooks')).toBeVisible();
  });

  test('hooks match on their trigger event, not just name and description', async () => {
    renderHub();
    await screen.findByText('code-review');

    fireEvent.change(screen.getByLabelText('Search all resources'), {
      target: { value: 'posttooluse' },
    });

    expect(await screen.findByText('lint-on-save')).toBeVisible();
  });
});

describe('ResourceHub deep links', () => {
  test('?kind= opens the kind the old per-kind URL named', async () => {
    renderHub('/settings/resources?kind=hooks');

    // Hooks sorts third in the kinds table, so landing on it can only be the
    // query param taking effect rather than the default first-kind pick.
    expect(await screen.findByText('lint-on-save')).toBeVisible();
    expect(screen.queryByText('code-review')).not.toBeInTheDocument();
  });

  test('without a kind param it opens the first kind that has anything', async () => {
    renderHub();

    expect(await screen.findByText('code-review')).toBeVisible();
  });
});

describe('ResourceHub failures', () => {
  test('one failing kind leaves the others usable', async () => {
    failing.add('/api/hooks');
    renderHub();

    expect(await screen.findByText('code-review')).toBeVisible();
    expect(screen.getByText(/Could not load/)).toBeVisible();
  });
});

describe('ResourceHub cards and detail view', () => {
  test('switching category swaps the listed cards', async () => {
    renderHub();
    await screen.findByText('code-review');
    expect(screen.getByText('lint-fix')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /^ops/ }));

    // dev's two cards leave with their category; ops' single one replaces them.
    await waitFor(() => expect(screen.getByText('deploy')).toBeVisible());
    expect(screen.queryByText('code-review')).not.toBeInTheDocument();
  });

  test('clicking a card opens the detail view, back returns to the list', async () => {
    renderHub();
    const card = (await screen.findByText('code-review')).closest(
      '[role="button"]',
    ) as HTMLElement;
    fireEvent.click(card);

    // Detail replaces the gallery; its primary heading is the item name.
    const detailHeading = await screen.findByRole('heading', {
      level: 1,
      name: 'code-review',
    });
    expect(detailHeading).toBeInTheDocument();
    expect(screen.queryByText('lint-fix')).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', { name: 'Back to the resource list' }),
    );
    await waitFor(() => expect(screen.getByText('lint-fix')).toBeVisible());
  });
});
