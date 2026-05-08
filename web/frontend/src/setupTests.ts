import '@testing-library/jest-dom';
import { vi } from 'vitest';

// Global mock for fetch
globalThis.fetch = vi.fn().mockImplementation((url: string) => {
  if (url.includes('/api/config')) {
    return Promise.resolve({
      ok: true,
      json: async () => ({
        default_mode: 'local',
        language: 'en',
        proxy: [],
        skills: { project_mapping: [] }
      }),
    });
  }
  if (url.includes('/api/skills')) {
    return Promise.resolve({
      ok: true,
      json: async () => ({
        base: [{ name: 'test-skill', id: 'base/test-skill', description: 'test', readme: 'test' }]
      }),
    });
  }
  if (url.includes('/api/prompts')) {
    return Promise.resolve({
      ok: true,
      json: async () => ([
        {
          id: 'base',
          name: 'base',
          description: 'test prompt group',
          readme: '## general.basic\n\ntest prompt',
          files: [{ name: 'general.basic', path: 'prompt/base/general.basic.md' }],
        },
      ]),
    });
  }
  if (url.includes('/api/projects')) {
    return Promise.resolve({
      ok: true,
      json: async () => [],
    });
  }
  if (url.includes('/api/groups')) {
    return Promise.resolve({
      ok: true,
      json: async () => ({
        codeagent: { skills: ['base/commit-message', 'base/local_code_review'], prompts: ['base'], hooks: [], plugins: [] },
        common:    { skills: ['base/commit-message'], prompts: [], hooks: [], plugins: [] },
      }),
    });
  }
  if (url.includes('/api/task')) {
    return Promise.resolve({
      ok: true,
      json: async () => ({ exists: false, tasks: [] }),
    });
  }
  return Promise.reject(new Error(`Unhandled fetch to ${url}`));
});
