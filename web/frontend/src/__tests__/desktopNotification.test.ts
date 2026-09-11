import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  isNotificationSupported,
  requestNotificationPermission,
  sendDesktopNotification,
} from '../utils/desktopNotification';

interface MockNotificationInstance {
  title: string;
  options?: NotificationOptions;
  onclick: ((this: Notification, ev: Event) => unknown) | null;
  close: ReturnType<typeof vi.fn>;
}

function createNotificationMock(permission: NotificationPermission = 'default') {
  const instances: MockNotificationInstance[] = [];

  const mockConstructor = vi.fn(function (title: string, options?: NotificationOptions) {
    const instance: MockNotificationInstance = {
      title,
      options,
      onclick: null,
      close: vi.fn(),
    };
    instances.push(instance);
    return instance;
  });

  const mockApi = Object.assign(mockConstructor, {
    permission,
    requestPermission: vi.fn(),
  });

  window.Notification = mockApi as unknown as typeof Notification;

  return {
    mockApi,
    instances,
    setPermission(perm: NotificationPermission) {
      mockApi.permission = perm;
    },
  };
}

describe('desktopNotification', () => {
  const originalNotification = window.Notification;

  afterEach(() => {
    vi.restoreAllMocks();
    if (originalNotification) {
      window.Notification = originalNotification;
    } else {
      delete (window as unknown as { Notification?: unknown }).Notification;
    }
  });

  describe('isNotificationSupported', () => {
    it('returns true when Notification exists in window', () => {
      createNotificationMock('default');
      expect(isNotificationSupported()).toBe(true);
    });

    it('returns false when Notification is not in window', () => {
      delete (window as unknown as { Notification?: unknown }).Notification;
      expect(isNotificationSupported()).toBe(false);
    });
  });

  describe('requestNotificationPermission', () => {
    it('returns denied if Notification is unsupported', async () => {
      delete (window as unknown as { Notification?: unknown }).Notification;
      const res = await requestNotificationPermission();
      expect(res).toBe('denied');
    });

    it('returns granted immediately if already granted without calling requestPermission', async () => {
      const { mockApi } = createNotificationMock('granted');

      const res = await requestNotificationPermission();
      expect(res).toBe('granted');
      expect(mockApi.requestPermission).not.toHaveBeenCalled();
    });

    it('calls requestPermission if permission is default', async () => {
      const { mockApi } = createNotificationMock('default');
      mockApi.requestPermission.mockResolvedValue('granted');

      const res = await requestNotificationPermission();
      expect(mockApi.requestPermission).toHaveBeenCalled();
      expect(res).toBe('granted');
    });

    it('handles requestPermission rejection gracefully', async () => {
      vi.spyOn(console, 'error').mockImplementation(() => {});
      const { mockApi } = createNotificationMock('denied');
      mockApi.requestPermission.mockRejectedValue(new Error('Permission prompt dismissed'));

      const res = await requestNotificationPermission();
      expect(res).toBe('denied');
    });
  });

  describe('sendDesktopNotification', () => {
    it('returns null if Notification is unsupported', () => {
      delete (window as unknown as { Notification?: unknown }).Notification;
      expect(sendDesktopNotification('Test')).toBeNull();
    });

    it('returns null if permission is default or denied', () => {
      const { setPermission, mockApi } = createNotificationMock('denied');

      expect(sendDesktopNotification('Test')).toBeNull();
      expect(mockApi).not.toHaveBeenCalled();

      setPermission('default');
      expect(sendDesktopNotification('Test')).toBeNull();
      expect(mockApi).not.toHaveBeenCalled();
    });

    it('instantiates Notification with title and options when granted', () => {
      const { mockApi, instances } = createNotificationMock('granted');

      const options: NotificationOptions = { body: 'Build succeeded', icon: '/favicon.ico' };
      const result = sendDesktopNotification('Finished', options);

      expect(mockApi).toHaveBeenCalledWith('Finished', options);
      expect(result).toBe(instances[0]);
    });

    it('handles click callback, focuses window, and closes notification', () => {
      const { instances } = createNotificationMock('granted');

      const focusSpy = vi.spyOn(window, 'focus').mockImplementation(() => {});
      const onClick = vi.fn();
      const mockEvent = { preventDefault: vi.fn() };

      sendDesktopNotification('Title', {}, onClick);

      expect(instances.length).toBe(1);
      const created = instances[0];
      expect(created.onclick).toBeDefined();
      created.onclick?.call(created as unknown as Notification, mockEvent as unknown as Event);

      expect(mockEvent.preventDefault).toHaveBeenCalled();
      expect(focusSpy).toHaveBeenCalled();
      expect(onClick).toHaveBeenCalled();
      expect(created.close).toHaveBeenCalled();
    });

    it('focuses window and closes notification even if onClick is omitted', () => {
      const { instances } = createNotificationMock('granted');

      const focusSpy = vi.spyOn(window, 'focus').mockImplementation(() => {});
      const mockEvent = { preventDefault: vi.fn() };

      sendDesktopNotification('Title');

      expect(instances.length).toBe(1);
      const created = instances[0];
      expect(created.onclick).toBeDefined();
      created.onclick?.call(created as unknown as Notification, mockEvent as unknown as Event);

      expect(mockEvent.preventDefault).toHaveBeenCalled();
      expect(focusSpy).toHaveBeenCalled();
      expect(created.close).toHaveBeenCalled();
    });

    it('catches and logs errors when new Notification throws', () => {
      const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      const mockConstructor = vi.fn(function () {
        throw new Error('Notification creation failed');
      });
      const mockApi = Object.assign(mockConstructor, {
        permission: 'granted' as NotificationPermission,
        requestPermission: vi.fn(),
      });
      window.Notification = mockApi as unknown as typeof Notification;

      const result = sendDesktopNotification('Error test');
      expect(result).toBeNull();
      expect(consoleErrorSpy).toHaveBeenCalled();
    });
  });
});
