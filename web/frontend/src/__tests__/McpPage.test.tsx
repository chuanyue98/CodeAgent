import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import McpPage from '../components/McpPage';
import { ProjectProvider } from '../context/ProjectContext';
import type { McpServer } from '../api/mcp';

function jsonResponse(data: unknown) {
  return Promise.resolve({
    ok: true,
    status: 200,
    text: async () => JSON.stringify(data),
    json: async () => data,
  });
}

const SERVER: McpServer = {
  name: 'search',
  scope: 'project',
  transport: 'stdio',
  command: ['npx', 'old-mcp-server'],
  url: null,
  env: { API_KEY: 'old-value' },
};

const SERVER_2: McpServer = {
  name: 'weather-api',
  scope: 'project',
  transport: 'http',
  command: null,
  url: 'https://weather.example.com/mcp',
  env: {},
};

let deleteCalls: string[];
let addCalls: unknown[];

beforeEach(() => {
  deleteCalls = [];
  addCalls = [];
  globalThis.fetch = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    const method = init?.method || 'GET';
    if (url.includes('/api/config')) return jsonResponse({});
    if (url.includes('/api/projects')) {
      return jsonResponse([{ path: '/workspace/proj', group: 'codeagent', available: true }]);
    }
    if (url.includes('/api/groups')) return jsonResponse({});
    if (url.includes('/api/engines')) return jsonResponse([{ id: 'claude', name: 'Claude' }]);
    if (url.startsWith('/api/mcp/claude/') && method === 'DELETE') {
      deleteCalls.push(url);
      return jsonResponse({ status: 'ok' });
    }
    if (url === '/api/mcp/claude' && method === 'POST') {
      addCalls.push(JSON.parse(init?.body as string));
      return jsonResponse({ status: 'ok' });
    }
    if (url.startsWith('/api/mcp/claude') && method === 'GET') {
      return jsonResponse([SERVER]);
    }
    return Promise.reject(new Error(`Unhandled fetch to ${url}`));
  }) as unknown as typeof fetch;
});

afterEach(() => {
  vi.restoreAllMocks();
});

function renderMcpPage() {
  return render(
    <MemoryRouter>
      <ProjectProvider>
        <McpPage />
      </ProjectProvider>
    </MemoryRouter>,
  );
}

describe('McpPage modal edit', () => {
  test('editing a server pre-fills the form and saves via remove-then-add', async () => {
    renderMcpPage();

    await screen.findByText('search');
    fireEvent.click(screen.getByRole('button', { name: '编辑 search' }));

    await screen.findByText('编辑 "search"');
    expect(screen.getByPlaceholderText('my-server')).toHaveValue('search');
    expect(screen.getByPlaceholderText('npx my-mcp-server --flag')).toHaveValue('npx old-mcp-server');
    expect(screen.getByPlaceholderText('API_KEY=xxx')).toHaveValue('API_KEY=old-value');

    fireEvent.change(screen.getByPlaceholderText('npx my-mcp-server --flag'), {
      target: { value: 'npx new-mcp-server' },
    });
    fireEvent.click(screen.getByRole('button', { name: '保存修改' }));

    await waitFor(() => {
      expect(deleteCalls).toHaveLength(1);
      expect(addCalls).toHaveLength(1);
    });
    expect(deleteCalls[0]).toContain('/api/mcp/claude/search');
    expect(addCalls[0]).toMatchObject({
      name: 'search',
      command: ['npx', 'new-mcp-server'],
      env: { API_KEY: 'old-value' },
    });

    await waitFor(() => {
      expect(screen.queryByText('编辑 "search"')).not.toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: /添加服务器/ })).toBeInTheDocument();
  });

  test('cancel edit closes the modal without calling the API', async () => {
    renderMcpPage();

    await screen.findByText('search');
    fireEvent.click(screen.getByRole('button', { name: '编辑 search' }));
    await screen.findByText('编辑 "search"');

    fireEvent.click(screen.getByRole('button', { name: '取消' }));

    await waitFor(() => {
      expect(screen.queryByText('编辑 "search"')).not.toBeInTheDocument();
    });
    expect(screen.queryByPlaceholderText('my-server')).not.toBeInTheDocument();
    expect(deleteCalls).toHaveLength(0);
    expect(addCalls).toHaveLength(0);
  });
});

describe('McpPage server search', () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      const method = init?.method || 'GET';
      if (url.includes('/api/config')) return jsonResponse({});
      if (url.includes('/api/projects')) {
        return jsonResponse([{ path: '/workspace/proj', group: 'codeagent', available: true }]);
      }
      if (url.includes('/api/groups')) return jsonResponse({});
      if (url.includes('/api/engines')) return jsonResponse([{ id: 'claude', name: 'Claude' }]);
      if (url.startsWith('/api/mcp/claude') && method === 'GET') {
        return jsonResponse([SERVER, SERVER_2]);
      }
      return Promise.reject(new Error(`Unhandled fetch to ${url}`));
    }) as unknown as typeof fetch;
  });

  test('filters the server list by name or command/url', async () => {
    renderMcpPage();

    await screen.findByText('search');
    expect(screen.getByText('weather-api')).toBeVisible();

    fireEvent.change(screen.getByLabelText('搜索服务器'), { target: { value: 'weather' } });

    expect(screen.getByText('weather-api')).toBeVisible();
    expect(screen.queryByText('search')).not.toBeInTheDocument();
  });

  test('shows an empty state when no server matches', async () => {
    renderMcpPage();

    await screen.findByText('search');
    fireEvent.change(screen.getByLabelText('搜索服务器'), { target: { value: 'nonexistent' } });

    expect(screen.getByText('没有匹配的服务器。')).toBeVisible();
  });
});
