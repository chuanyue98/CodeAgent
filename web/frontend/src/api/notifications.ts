import request from '../utils/request';

export interface NotificationItem {
  id: number;
  createdAt: number;
  scheduleId: string | null;
  taskId: string | null;
  taskName: string | null;
  engine: string | null;
  status: string;
  title: string;
  summary: string | null;
  readAt: number | null;
}

export interface UnreadCountResponse {
  count: number;
}

export async function fetchNotifications(options?: {
  limit?: number;
  unreadOnly?: boolean;
}): Promise<NotificationItem[]> {
  const params = new URLSearchParams();
  if (options?.limit !== undefined) {
    params.set('limit', String(options.limit));
  }
  if (options?.unreadOnly !== undefined) {
    params.set('unread_only', String(options.unreadOnly));
  }
  const query = params.toString();
  return request<NotificationItem[]>(`/api/notifications${query ? `?${query}` : ''}`);
}

export async function fetchUnreadCount(): Promise<number> {
  const res = await request<UnreadCountResponse>('/api/notifications/unread-count');
  return res.count;
}

export async function markNotificationRead(id: number): Promise<void> {
  await request<{ status: string }>(`/api/notifications/${id}/read`, {
    method: 'POST',
  });
}

export async function markAllNotificationsRead(): Promise<number> {
  const res = await request<{ marked: number }>('/api/notifications/read-all', {
    method: 'POST',
  });
  return res.marked;
}
