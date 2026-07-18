import '@testing-library/jest-dom';
import { vi } from 'vitest';

// Helper to create a mock Response with both text() and json()
function mockResponse(data: unknown) {
  const text = JSON.stringify(data);
  return {
    ok: true,
    status: 200,
    text: async () => text,
    json: async () => data,
  };
}

// Global mock for fetch
globalThis.fetch = vi.fn().mockImplementation((url: string) => {
  if (url.includes('/api/config')) {
    return Promise.resolve(mockResponse({
      default_mode: 'local',
      language: 'en',
      proxy: [],
      skills: { project_mapping: [] }
    }));
  }
  if (url.includes('/api/skills')) {
    return Promise.resolve(mockResponse({
      base: [{ name: 'test-skill', id: 'base/test-skill', description: 'test', readme: 'test' }]
    }));
  }
  if (url.includes('/api/prompts')) {
    return Promise.resolve(mockResponse([
      {
        id: 'base',
        name: 'base',
        description: 'test prompt group',
        readme: '## general.basic\n\ntest prompt',
        files: [{ name: 'general.basic', path: 'prompt/base/general.basic.md' }],
      },
    ]));
  }
  if (url.includes('/api/projects')) {
    return Promise.resolve(mockResponse([]));
  }
  if (url.includes('/api/groups')) {
    return Promise.resolve(mockResponse({
      codeagent: { skills: ['base/commit-message', 'base/local_code_review'], prompts: ['base'], hooks: [], plugins: [] },
      common:    { skills: ['base/commit-message'], prompts: [], hooks: [], plugins: [] },
    }));
  }
  if (url.endsWith('/api/tasks')) {
    return Promise.resolve(mockResponse([]));
  }
  if (url.includes('/api/task')) {
    return Promise.resolve(mockResponse({ exists: false, tasks: [] }));
  }
  if (url.includes('/api/system/metrics')) {
    return Promise.resolve(mockResponse({
      cpu_percent: 10,
      memory_percent: 20,
      memory_used_gb: 2,
      memory_total_gb: 16,
      disk_percent: 30,
      disk_used_gb: 10,
      disk_total_gb: 100,
      uptime_seconds: 3600,
      history_file_size_mb: 0,
      log_file_count: 0,
    }));
  }
  if (url.includes('/api/engines')) {
    return Promise.resolve(mockResponse([]));
  }
  if (url.includes('/api/hooks')) {
    return Promise.resolve(mockResponse([]));
  }
  if (url.includes('/api/plugins')) {
    return Promise.resolve(mockResponse({}));
  }
  return Promise.reject(new Error(`Unhandled fetch to ${url}`));
});
