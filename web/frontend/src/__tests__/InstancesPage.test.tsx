import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import InstancesPage from '../components/InstancesPage';

function instance(overrides: Record<string, unknown> = {}) {
  return {
    kind: 'chat',
    id: 'ins-1',
    engine: 'claude',
    cwd: '/workspace/proj',
    title: 'A chat',
    status: 'disconnected',
    pid: null,
    startedAt: new Date(Date.now() - 45 * 24 * 3600 * 1000).toISOString(),
    stoppable: false,
    ...overrides,
  };
}

function mockInstances(instances: ReturnType<typeof instance>[]) {
  globalThis.fetch = vi.fn().mockImplementation(() =>
    Promise.resolve({
      ok: true,
      status: 200,
      text: async () => JSON.stringify({ instances }),
      json: async () => ({ instances }),
    }),
  ) as typeof fetch;
}

const originalFetch = globalThis.fetch;

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  globalThis.fetch = originalFetch;
});

test('the header separates what is running from what is merely listed', async () => {
  // Everything here is finished, so "3 instances running" over three rows was
  // the page contradicting itself.
  mockInstances([
    instance({ id: 'a' }),
    instance({ id: 'b' }),
    instance({ id: 'c', status: 'running', stoppable: true }),
  ]);
  render(<InstancesPage />);

  expect(await screen.findByText('1 running · 3 listed')).toBeInTheDocument();
});

test('an age past two days is counted in days, not hours', async () => {
  mockInstances([instance({ id: 'a' })]);
  render(<InstancesPage />);

  // 45 days in, hours stopped carrying meaning ("1081h 59min").
  expect(await screen.findByText('45d')).toBeInTheDocument();
});
