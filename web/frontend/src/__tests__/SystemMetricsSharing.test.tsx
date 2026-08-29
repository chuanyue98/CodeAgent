import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, test, vi } from 'vitest';
import SystemPanel from '../components/SystemPanel';
import SystemPage from '../pages/SystemPage';
import { SystemMetricsProvider } from '../context/SystemMetricsContext';
import { fetchSystemHealth, fetchSystemMetrics, type SystemMetrics } from '../api/system';

vi.mock('../api/system', () => ({
  fetchSystemMetrics: vi.fn(),
  fetchSystemHealth: vi.fn(),
}));

// LogViewer does its own fetch/polling unrelated to this test; stub it out.
vi.mock('../components/LogViewer', () => ({ default: () => null }));

const metrics: SystemMetrics = {
  cpuPercent: 42,
  memoryPercent: 34,
  memoryUsedGb: 5,
  memoryTotalGb: 16,
  diskPercent: 56,
  diskUsedGb: 50,
  diskTotalGb: 100,
  uptimeSeconds: 7200,
  historyFileSizeMb: 1.5,
  logFileCount: 3,
};

afterEach(() => {
  vi.mocked(fetchSystemMetrics).mockReset();
  vi.mocked(fetchSystemHealth).mockReset();
});

describe('SystemPanel and SystemPage share one metrics subscription', () => {
  test('both views render the same value from a single fetch', async () => {
    vi.mocked(fetchSystemMetrics).mockResolvedValue(metrics);
    vi.mocked(fetchSystemHealth).mockResolvedValue({ status: 'ok', sections: [] });

    render(
      <SystemMetricsProvider>
        <SystemPanel />
        <SystemPage />
      </SystemMetricsProvider>,
    );
    await act(async () => {});

    // SystemPage renders its own "42%" for CPU immediately (metrics section);
    // SystemPanel keeps its copy hidden until opened.
    expect(await screen.findAllByText('42%')).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: 'System status' }));
    expect(screen.getAllByText('42%')).toHaveLength(2);

    // One shared subscription, not one fetch per consumer.
    expect(fetchSystemMetrics).toHaveBeenCalledTimes(1);
  });

  test("SystemPage's Refresh button also refreshes the shared metrics", async () => {
    vi.mocked(fetchSystemMetrics).mockResolvedValue(metrics);
    vi.mocked(fetchSystemHealth).mockResolvedValue({ status: 'ok', sections: [] });

    render(
      <SystemMetricsProvider>
        <SystemPanel />
        <SystemPage />
      </SystemMetricsProvider>,
    );
    await act(async () => {});
    expect(fetchSystemMetrics).toHaveBeenCalledTimes(1);

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
    });

    expect(fetchSystemMetrics).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByRole('button', { name: 'System status' }));
    expect(screen.getAllByText('42%')).toHaveLength(2);
  });
});
