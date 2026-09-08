import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, test, vi } from 'vitest';
import { MemoryRouter } from 'react-router';
import NotificationBell from '../components/NotificationBell';
import type { NotificationItem } from '../api/notifications';

function jsonResponse(data: unknown) {
  return Promise.resolve({
    ok: true,
    status: 200,
    text: async () => JSON.stringify(data),
    json: async () => data,
  });
}

const mockNavigate = vi.fn();
vi.mock('react-router', async () => {
  const actual = await vi.importActual('react-router');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

const NOTIFICATIONS: NotificationItem[] = [
  {
    id: 1,
    createdAt: 1725200000,
    scheduleId: 'sched-1',
    taskId: 'run-123',
    taskName: 'daily-build',
    engine: 'claude',
    status: 'success',
    title: 'Daily Build succeeded',
    summary: 'Build finished in 45s without errors.',
    readAt: null,
  },
  {
    id: 2,
    createdAt: 1725100000,
    scheduleId: 'sched-2',
    taskId: 'run-124',
    taskName: 'code-review',
    engine: 'claude',
    status: 'failure',
    title: 'Code Review failed',
    summary: 'Lint errors detected in 3 files.',
    readAt: 1725150000,
  },
];

let markedIds: number[] = [];
let markedAll = false;

beforeEach(() => {
  mockNavigate.mockReset();
  markedIds = [];
  markedAll = false;

  globalThis.fetch = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    if (url.includes('/api/notifications/unread-count')) {
      return jsonResponse({ count: markedAll ? 0 : 1 });
    }
    if (url.startsWith('/api/notifications/read-all') && init?.method === 'POST') {
      markedAll = true;
      return jsonResponse({ marked: 1 });
    }
    if (url.match(/\/api\/notifications\/\d+\/read/) && init?.method === 'POST') {
      const id = Number(url.split('/')[3]);
      markedIds.push(id);
      return jsonResponse({ status: 'ok' });
    }
    if (url.startsWith('/api/notifications')) {
      return jsonResponse(
        NOTIFICATIONS.map(n => ({
          ...n,
          readAt: markedAll || markedIds.includes(n.id) ? 1725200001 : n.readAt,
        })),
      );
    }
    return Promise.reject(new Error(`Unhandled fetch to ${url}`));
  }) as unknown as typeof fetch;
});

function renderBell() {
  return render(
    <MemoryRouter>
      <NotificationBell />
    </MemoryRouter>,
  );
}

describe('NotificationBell', () => {
  test('renders bell button and badge with unread count', async () => {
    renderBell();

    const button = screen.getByTestId('notification-bell-button');
    expect(button).toBeVisible();

    const badge = await screen.findByTestId('notification-unread-badge');
    expect(badge).toHaveTextContent('1');
  });

  test('clicking bell opens dropdown and lists notifications', async () => {
    renderBell();

    const button = screen.getByTestId('notification-bell-button');
    fireEvent.click(button);

    const dropdown = await screen.findByTestId('notification-dropdown');
    expect(dropdown).toBeVisible();

    expect(await screen.findByText('Daily Build succeeded')).toBeVisible();
    expect(screen.getByText('Code Review failed')).toBeVisible();
    expect(screen.getByText(/Build finished in 45s/)).toBeVisible();
  });

  test('clicking an unread item marks it as read and navigates to session', async () => {
    renderBell();

    const button = screen.getByTestId('notification-bell-button');
    fireEvent.click(button);

    const item = await screen.findByTestId('notification-item-1');
    fireEvent.click(item);

    await waitFor(() => {
      expect(markedIds).toContain(1);
    });
    expect(mockNavigate).toHaveBeenCalledWith('/activity/sessions?session=run-123');
    expect(screen.queryByTestId('notification-dropdown')).not.toBeInTheDocument();
  });

  test('mark all read button triggers markAllNotificationsRead', async () => {
    renderBell();

    const button = screen.getByTestId('notification-bell-button');
    fireEvent.click(button);

    const markAllBtn = await screen.findByText(/Mark all read|全部已读/i);
    fireEvent.click(markAllBtn);

    await waitFor(() => {
      expect(markedAll).toBe(true);
    });
  });

  test('pressing Escape closes the dropdown', async () => {
    renderBell();

    const button = screen.getByTestId('notification-bell-button');
    fireEvent.click(button);

    expect(await screen.findByTestId('notification-dropdown')).toBeVisible();

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByTestId('notification-dropdown')).not.toBeInTheDocument();
  });
});
