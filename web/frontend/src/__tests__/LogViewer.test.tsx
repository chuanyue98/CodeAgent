import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import LogViewer from '../components/LogViewer';
import * as logsApi from '../api/logs';

vi.mock('../api/logs', () => ({
  fetchLogFiles: vi.fn(),
  fetchLogFile: vi.fn(),
  useLogStream: vi.fn(),
}));

const mockFiles: logsApi.LogFile[] = [
  { taskId: 'task-1', name: 'task-1.log', size: 1024, modified: 1600000000 },
  { taskId: 'task-2', name: 'task-2.log', size: 2048, modified: 1600000010 },
];

describe('LogViewer', () => {
  let writeTextMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.clearAllMocks();
    writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    vi.mocked(logsApi.fetchLogFiles).mockResolvedValue(mockFiles);
    vi.mocked(logsApi.fetchLogFile).mockImplementation(async (taskId: string) => {
      if (taskId === 'task-1') {
        return {
          taskId: 'task-1',
          content: '[INFO] Starting application\n[WARN] Low disk space\n[ERROR] Failed to bind port\n[INFO] Shutdown complete',
        };
      }
      return {
        taskId,
        content: `Log content for ${taskId}`,
      };
    });

    vi.mocked(logsApi.useLogStream).mockReturnValue({
      lines: [],
      error: null,
      connected: false,
      finished: null,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  test('renders file list and loads logs when a file is selected', async () => {
    render(<LogViewer />);

    await waitFor(() => {
      expect(screen.getByText('task-1.log')).toBeInTheDocument();
      expect(screen.getByText('task-2.log')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('task-1.log'));

    await waitFor(() => {
      expect(screen.getByText(/\[INFO\] Starting application/)).toBeInTheDocument();
      expect(screen.getByText(/\[ERROR\] Failed to bind port/)).toBeInTheDocument();
    });
  });

  test('loads initial task logs when taskId prop is provided', async () => {
    render(<LogViewer taskId="task-1" />);

    await waitFor(() => {
      expect(screen.getByText(/\[INFO\] Starting application/)).toBeInTheDocument();
    });
  });

  test('filters logs by keyword (case-insensitive), shows empty state on 0 matches, and restores on clear', async () => {
    render(<LogViewer taskId="task-1" />);

    await waitFor(() => {
      expect(screen.getByText(/\[INFO\] Starting application/)).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText('Filter logs...');

    // Filter by "error" (case-insensitive)
    fireEvent.change(searchInput, { target: { value: 'error' } });

    expect(screen.getByText(/\[ERROR\] Failed to bind port/)).toBeInTheDocument();
    expect(screen.queryByText(/\[INFO\] Starting application/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\[WARN\] Low disk space/)).not.toBeInTheDocument();

    // Filter by non-matching query
    fireEvent.change(searchInput, { target: { value: 'nonexistent-pattern' } });
    expect(screen.getByText('匹配 0 行')).toBeInTheDocument();

    // Clear search
    fireEvent.change(searchInput, { target: { value: '' } });
    expect(screen.getByText(/\[INFO\] Starting application/)).toBeInTheDocument();
    expect(screen.getByText(/\[WARN\] Low disk space/)).toBeInTheDocument();
    expect(screen.getByText(/\[ERROR\] Failed to bind port/)).toBeInTheDocument();
  });

  test('copies all lines or filtered lines to clipboard and shows copied feedback for 2 seconds', async () => {
    render(<LogViewer taskId="task-1" />);

    // Wait for content to load under real timers
    await waitFor(() => {
      expect(screen.getByText(/\[INFO\] Starting application/)).toBeInTheDocument();
    });

    vi.useFakeTimers();
    const copyBtn = screen.getByRole('button', { name: /Copy all/i });
    await act(async () => {
      fireEvent.click(copyBtn);
    });

    expect(writeTextMock).toHaveBeenCalledWith(
      '[INFO] Starting application\n[WARN] Low disk space\n[ERROR] Failed to bind port\n[INFO] Shutdown complete',
    );

    expect(screen.getByText('Copied')).toBeInTheDocument();

    // After 2 seconds, reverts back
    await act(async () => {
      vi.advanceTimersByTime(2000);
    });
    expect(screen.getByText('Copy all')).toBeInTheDocument();

    // Now test copy with filter active
    const searchInput = screen.getByPlaceholderText('Filter logs...');
    act(() => {
      fireEvent.change(searchInput, { target: { value: 'low disk' } });
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Copy all/i }));
    });

    expect(writeTextMock).toHaveBeenLastCalledWith('[WARN] Low disk space');
  });

  test('toggles auto-scroll status', async () => {
    render(<LogViewer taskId="task-1" />);

    await waitFor(() => {
      expect(screen.getByText(/\[INFO\] Starting application/)).toBeInTheDocument();
    });

    const toggleBtn = screen.getByRole('button', { name: /Auto-scroll ON/i });
    expect(toggleBtn).toBeInTheDocument();

    fireEvent.click(toggleBtn);
    expect(screen.getByRole('button', { name: /Auto-scroll OFF/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Auto-scroll OFF/i }));
    expect(screen.getByRole('button', { name: /Auto-scroll ON/i })).toBeInTheDocument();
  });

  test('toggles fullscreen mode with button and exits on Escape key', async () => {
    const { container } = render(<LogViewer taskId="task-1" />);

    await waitFor(() => {
      expect(screen.getByText(/\[INFO\] Starting application/)).toBeInTheDocument();
    });

    const rootCard = container.firstElementChild as HTMLElement;
    expect(rootCard.className).not.toContain('fixed inset-0');

    // Click fullscreen button
    const fullscreenBtn = screen.getByRole('button', { name: 'Fullscreen' });
    fireEvent.click(fullscreenBtn);

    expect(rootCard.className).toContain('fixed inset-0 z-50 p-4 bg-white/95 backdrop-blur-md');
    expect(screen.getByRole('button', { name: 'Exit fullscreen' })).toBeInTheDocument();

    // Press Escape to exit fullscreen
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(rootCard.className).not.toContain('fixed inset-0');
    expect(screen.getByRole('button', { name: 'Fullscreen' })).toBeInTheDocument();

    // Click fullscreen then click exit button
    fireEvent.click(screen.getByRole('button', { name: 'Fullscreen' }));
    expect(rootCard.className).toContain('fixed inset-0');

    fireEvent.click(screen.getByRole('button', { name: 'Exit fullscreen' }));
    expect(rootCard.className).not.toContain('fixed inset-0');
  });
});
