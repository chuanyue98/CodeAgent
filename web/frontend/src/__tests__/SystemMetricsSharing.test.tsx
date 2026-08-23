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
  cpu_percent: 42,
  memory_percent: 34,
  memory_used_gb: 5,
  memory_total_gb: 16,
  disk_percent: 56,
  disk_used_gb: 50,
  disk_total_gb: 100,
  uptime_seconds: 7200,
  history_file_size_mb: 1.5,
  log_file_count: 3,
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
    fireEvent.click(screen.getByRole('button', { name: '系统状态' }));
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
      fireEvent.click(screen.getByRole('button', { name: '刷新' }));
    });

    expect(fetchSystemMetrics).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByRole('button', { name: '系统状态' }));
    expect(screen.getAllByText('42%')).toHaveLength(2);
  });
});
