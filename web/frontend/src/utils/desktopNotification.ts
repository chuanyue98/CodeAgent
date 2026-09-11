/**
 * Checks if the Web Notifications API is supported in the current environment.
 */
export function isNotificationSupported(): boolean {
  return typeof window !== 'undefined' && 'Notification' in window;
}

/**
 * Requests notification permission from the user if not already granted or denied.
 * Returns 'granted', 'denied', or 'default'.
 */
export async function requestNotificationPermission(): Promise<NotificationPermission> {
  if (!isNotificationSupported()) {
    return 'denied';
  }

  if (Notification.permission === 'granted') {
    return 'granted';
  }

  try {
    const permission = await Notification.requestPermission();
    return permission;
  } catch (error) {
    console.error('Failed to request notification permission:', error);
    return Notification.permission;
  }
}

/**
 * Sends a desktop notification if permission is granted and Notification API is available.
 * Attaches an optional click handler that focuses the window and executes the callback.
 */
export function sendDesktopNotification(
  title: string,
  options?: NotificationOptions,
  onClick?: () => void,
): Notification | null {
  if (!isNotificationSupported()) {
    return null;
  }

  if (Notification.permission !== 'granted') {
    return null;
  }

  try {
    const notification = new Notification(title, options);

    if (onClick) {
      notification.onclick = (event) => {
        event.preventDefault();
        window.focus();
        onClick();
      };
    }

    return notification;
  } catch (error) {
    console.error('Failed to send desktop notification:', error);
    return null;
  }
}
