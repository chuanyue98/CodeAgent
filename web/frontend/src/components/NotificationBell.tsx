import { useEffect, useRef, useState, useCallback } from 'react';
import { useNavigate } from 'react-router';
import { Bell, CheckCircle2, AlertTriangle, XCircle, Clock, CheckCheck } from 'lucide-react';
import {
  fetchNotifications,
  fetchUnreadCount,
  markNotificationRead,
  markAllNotificationsRead,
  type NotificationItem,
} from '../api/notifications';
import { useIsMounted } from '../hooks/useAsyncGuards';
import usePolling from '../hooks/usePolling';
import { useT } from '../i18n/context';

const POLL_INTERVAL_MS = 30000;

function formatTimestamp(ts: number): string {
  return new Date(ts * 1000).toLocaleString();
}

function StatusIcon({ status }: { status: string }) {
  switch (status.toLowerCase()) {
    case 'success':
      return <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-500" />;
    case 'failure':
    case 'error':
      return <AlertTriangle className="h-4 w-4 shrink-0 text-rose-500" />;
    case 'cancelled':
    case 'canceled':
      return <XCircle className="h-4 w-4 shrink-0 text-slate-400" />;
    default:
      return <Clock className="h-4 w-4 shrink-0 text-blue-500" />;
  }
}

export default function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState(false);
  const isMounted = useIsMounted();
  const t = useT();
  const navigate = useNavigate();
  const containerRef = useRef<HTMLDivElement>(null);

  const refreshUnread = useCallback(async () => {
    try {
      const count = await fetchUnreadCount();
      if (isMounted()) {
        setUnreadCount(count);
      }
    } catch {
      // Ignore network errors during poll
    }
  }, [isMounted]);

  usePolling(refreshUnread, POLL_INTERVAL_MS);

  const loadNotifications = useCallback(async () => {
    setLoading(true);
    try {
      const list = await fetchNotifications({ limit: 50 });
      if (isMounted()) {
        setNotifications(list);
      }
    } catch {
      // Ignore network errors
    } finally {
      if (isMounted()) {
        setLoading(false);
      }
    }
  }, [isMounted]);

  const handleToggle = () => {
    const nextOpen = !open;
    setOpen(nextOpen);
    if (nextOpen) {
      void loadNotifications();
      void refreshUnread();
    }
  };

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, []);

  const handleItemClick = async (item: NotificationItem) => {
    if (item.readAt === null) {
      try {
        await markNotificationRead(item.id);
        setNotifications(prev =>
          prev.map(n => (n.id === item.id ? { ...n, readAt: Date.now() / 1000 } : n)),
        );
        setUnreadCount(prev => Math.max(0, prev - 1));
      } catch {
        // Continue navigation even if marking read fails
      }
    }
    setOpen(false);
    if (item.taskId) {
      navigate(`/activity/sessions?session=${encodeURIComponent(item.taskId)}`);
    } else if (item.scheduleId) {
      navigate('/automations/schedules');
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await markAllNotificationsRead();
      const now = Date.now() / 1000;
      setNotifications(prev => prev.map(n => ({ ...n, readAt: n.readAt ?? now })));
      setUnreadCount(0);
    } catch {
      // Ignore error
    }
  };

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        data-testid="notification-bell-button"
        onClick={handleToggle}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={t('notifications.openPanel')}
        title={t('notifications.openPanel')}
        className="relative flex items-center gap-1.5 rounded-xl border border-slate-100 bg-white/50 px-3 py-2 text-slate-500 shadow-sm backdrop-blur-md transition-colors hover:bg-white hover:text-slate-800"
      >
        <Bell size={16} />
        {unreadCount > 0 && (
          <span
            data-testid="notification-unread-badge"
            className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-bold text-white shadow-sm ring-2 ring-white"
          >
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div
          data-testid="notification-dropdown"
          role="dialog"
          aria-label={t('notifications.title')}
          className="glass-card absolute right-0 z-50 mt-2 w-80 sm:w-96 max-w-[calc(100vw-1rem)] overflow-hidden p-0 shadow-xl"
        >
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
            <span className="text-xs font-semibold text-slate-700">
              {t('notifications.title')}
            </span>
            {unreadCount > 0 && (
              <button
                type="button"
                onClick={handleMarkAllRead}
                className="flex items-center gap-1 text-[11px] font-medium text-primary hover:underline"
              >
                <CheckCheck size={13} />
                {t('notifications.markAllRead')}
              </button>
            )}
          </div>

          <div className="max-h-80 overflow-y-auto divide-y divide-slate-100">
            {loading && notifications.length === 0 ? (
              <div className="p-6 text-center text-xs text-slate-400">
                Loading...
              </div>
            ) : notifications.length === 0 ? (
              <div className="p-6 text-center text-xs text-slate-400">
                {t('notifications.none')}
              </div>
            ) : (
              notifications.map(item => {
                const isUnread = item.readAt === null;
                return (
                  <div
                    key={item.id}
                    data-testid={`notification-item-${item.id}`}
                    onClick={() => void handleItemClick(item)}
                    className={`flex cursor-pointer items-start gap-3 p-3 transition-colors hover:bg-slate-50/80 ${
                      isUnread ? 'bg-primary/[0.03]' : ''
                    }`}
                  >
                    <div className="mt-0.5">
                      <StatusIcon status={item.status} />
                    </div>
                    <div className="min-w-0 flex-1 space-y-0.5">
                      <div className="flex items-center justify-between gap-1">
                        <span className={`text-xs truncate ${isUnread ? 'font-semibold text-slate-800' : 'font-normal text-slate-600'}`}>
                          {item.title || item.taskName || 'Notification'}
                        </span>
                        {isUnread && (
                          <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                        )}
                      </div>
                      {item.summary && (
                        <p className="line-clamp-2 text-[11px] text-slate-500 whitespace-pre-line">
                          {item.summary}
                        </p>
                      )}
                      <div className="flex items-center gap-2 pt-0.5 text-[10px] text-slate-400">
                        {item.engine && <span>{item.engine}</span>}
                        <span>{formatTimestamp(item.createdAt)}</span>
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
