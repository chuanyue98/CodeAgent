import { act, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, test, vi } from 'vitest';
import SystemPanel from '../components/SystemPanel';
import { fetchSystemMetrics, type SystemMetrics } from '../api/system';

vi.mock('../api/system', () => ({
  fetchSystemMetrics: vi.fn(),
}));

const metrics: SystemMetrics = {
  cpu_percent: 12,
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

describe('SystemPanel', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.mocked(fetchSystemMetrics).mockReset();
  });

  test('clears a transient error when the next metrics poll succeeds', async () => {
    vi.useFakeTimers();
    vi.mocked(fetchSystemMetrics)
      .mockRejectedValueOnce(new Error('Failed to fetch system metrics'))
      .mockResolvedValue(metrics);

    render(<SystemPanel />);
    await act(async () => {});
    expect(screen.getByText('Failed to fetch system metrics')).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });

    expect(screen.queryByText('Failed to fetch system metrics')).not.toBeInTheDocument();
    expect(screen.getByText('12%')).toBeInTheDocument();
  });
});
