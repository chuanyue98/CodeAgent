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
      cpuPercent: 10,
      memoryPercent: 20,
      memoryUsedGb: 2,
      memoryTotalGb: 16,
      diskPercent: 30,
      diskUsedGb: 10,
      diskTotalGb: 100,
      uptimeSeconds: 3600,
      historyFileSizeMb: 0,
      logFileCount: 0,
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

// Node 26's experimental `localStorage` global is disabled without
// --localstorage-file and surfaces as `undefined`; jsdom's own storage is
// likewise unavailable on its default opaque origin. Components read the
// bare `localStorage` global, so give tests an in-memory implementation.
if (typeof globalThis.localStorage === 'undefined' || globalThis.localStorage === null) {
  const memory = new Map<string, string>();
  const storage: Storage = {
    get length() {
      return memory.size;
    },
    clear: () => memory.clear(),
    getItem: key => (memory.has(key) ? memory.get(key)! : null),
    key: index => Array.from(memory.keys())[index] ?? null,
    removeItem: key => {
      memory.delete(key);
    },
    setItem: (key, value) => {
      memory.set(key, String(value));
    },
  };
  Object.defineProperty(globalThis, 'localStorage', {
    value: storage,
    configurable: true,
    writable: true,
  });
}

// Not implemented by the DOM environment used here, and every listbox that
// keeps its focused option in view calls it during a passive effect — where a
// throw is not caught by anything and fails the render outright.
if (typeof Element !== 'undefined' && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
