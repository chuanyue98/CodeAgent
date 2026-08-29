import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, test, vi } from 'vitest';
import SystemPanel from '../components/SystemPanel';
import { SystemMetricsProvider } from '../context/SystemMetricsContext';
import { fetchSystemMetrics, type SystemMetrics } from '../api/system';

vi.mock('../api/system', () => ({
  fetchSystemMetrics: vi.fn(),
}));

function renderPanel() {
  return render(
    <SystemMetricsProvider>
      <SystemPanel />
    </SystemMetricsProvider>,
  );
}

const metrics: SystemMetrics = {
  cpuPercent: 12,
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

describe('SystemPanel', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.mocked(fetchSystemMetrics).mockReset();
  });

  test('metrics stay tucked away in the status popover until the button is clicked', async () => {
    vi.mocked(fetchSystemMetrics).mockResolvedValue(metrics);

    renderPanel();
    await act(async () => {});

    expect(screen.queryByText('12%')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'System status' }));
    expect(screen.getByText('12%')).toBeInTheDocument();
  });

  test('clears a transient error when the next metrics poll succeeds', async () => {
    vi.useFakeTimers();
    vi.mocked(fetchSystemMetrics)
      .mockRejectedValueOnce(new Error('Failed to fetch system metrics'))
      .mockResolvedValue(metrics);

    renderPanel();
    await act(async () => {});

    fireEvent.click(screen.getByRole('button', { name: 'System status' }));
    expect(screen.getByText('Failed to fetch system metrics')).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });

    expect(screen.queryByText('Failed to fetch system metrics')).not.toBeInTheDocument();
    expect(screen.getByText('12%')).toBeInTheDocument();
  });
});
