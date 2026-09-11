import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';

/**
 * xterm draws to a canvas jsdom does not have, so the terminal itself is a
 * stand-in. What is under test is the wiring around it: which socket gets
 * opened, what reaches the terminal, and which of "exited" and "disconnected"
 * the banner ends up showing.
 */
const terminals: FakeTerminal[] = [];

class FakeTerminal {
  cols = 80;
  rows = 24;
  written: string[] = [];
  disposed = false;
  focused = 0;
  cleared = 0;
  selection = 'scrollback text';
  private dataHandler: ((data: string) => void) | null = null;

  constructor() {
    terminals.push(this);
  }
  loadAddon() {}
  open() {}
  focus() {
    this.focused += 1;
  }
  write(data: string) {
    this.written.push(data);
  }
  clear() {
    this.cleared += 1;
  }
  selectAll() {}
  getSelection() {
    return this.selection;
  }
  clearSelection() {}
  dispose() {
    this.disposed = true;
  }
  onData(handler: (data: string) => void) {
    this.dataHandler = handler;
    return { dispose: () => { this.dataHandler = null; } };
  }
  type(data: string) {
    this.dataHandler?.(data);
  }
}

vi.mock('@xterm/xterm', () => ({ Terminal: FakeTerminal }));
vi.mock('@xterm/addon-fit', () => ({ FitAddon: class { fit() {} } }));
vi.mock('@xterm/xterm/css/xterm.css', () => ({}));

const sockets: FakeSocket[] = [];

class FakeSocket {
  static readonly OPEN = 1;
  static readonly CLOSED = 3;
  readyState = 1;
  sent: string[] = [];
  closed = false;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: ((event: { reason: string }) => void) | null = null;

  url: string;

  constructor(url: string) {
    this.url = url;
    sockets.push(this);
  }
  send(data: string) {
    this.sent.push(data);
  }
  close() {
    this.closed = true;
    this.readyState = 3;
  }
  emit(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) });
  }
}

const originalWebSocket = globalThis.WebSocket;
let BrowserTerminal: typeof import('../components/BrowserTerminal').default;

const mockNotificationInstances: Array<{
  title: string;
  options?: NotificationOptions;
  onclick: ((event: Event) => void) | null;
  close: ReturnType<typeof vi.fn>;
}> = [];

const mockNotificationConstructor = vi.fn(function (title: string, options?: NotificationOptions) {
  const instance = {
    title,
    options,
    onclick: null,
    close: vi.fn(),
  };
  mockNotificationInstances.push(instance);
  return instance;
});

const mockNotificationApi = Object.assign(mockNotificationConstructor, {
  permission: 'granted' as NotificationPermission,
  requestPermission: vi.fn().mockResolvedValue('granted' as NotificationPermission),
});

const originalNotification = window.Notification;
let originalHiddenDescriptor: PropertyDescriptor | undefined;

function setDocumentHidden(hidden: boolean) {
  Object.defineProperty(document, 'hidden', {
    value: hidden,
    configurable: true,
    writable: true,
  });
}

beforeEach(async () => {
  terminals.length = 0;
  sockets.length = 0;
  mockNotificationInstances.length = 0;
  mockNotificationConstructor.mockClear();
  mockNotificationApi.permission = 'granted';
  window.Notification = mockNotificationApi as unknown as typeof Notification;

  originalHiddenDescriptor =
    Object.getOwnPropertyDescriptor(Document.prototype, 'hidden') ||
    Object.getOwnPropertyDescriptor(document, 'hidden');
  setDocumentHidden(false);
  document.title = 'CodeAgent Test';

  globalThis.WebSocket = FakeSocket as unknown as typeof WebSocket;
  globalThis.ResizeObserver = class {
    observe() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
  BrowserTerminal = (await import('../components/BrowserTerminal')).default;
});

afterEach(() => {
  cleanup();
  globalThis.WebSocket = originalWebSocket;
  if (originalNotification) {
    window.Notification = originalNotification;
  } else {
    delete (window as unknown as { Notification?: unknown }).Notification;
  }
  if (originalHiddenDescriptor) {
    Object.defineProperty(document, 'hidden', originalHiddenDescriptor);
  } else {
    delete (document as unknown as { hidden?: unknown }).hidden;
  }
});

function open(props: Parameters<typeof BrowserTerminal>[0] extends infer P ? Partial<P> : never = {}) {
  return render(
    <BrowserTerminal engine="claude" cwd="/workspace/project-a" {...props} />,
  );
}

test('the socket carries the engine and workspace it was opened for', () => {
  open();

  expect(sockets[0].url).toContain('engine=claude');
  expect(sockets[0].url).toContain('cwd=%2Fworkspace%2Fproject-a');
  expect(sockets[0].url).not.toContain('session_id');
});

test('resuming names the session the server should hand to the engine', () => {
  open({ sessionId: 'session-a' });

  expect(sockets[0].url).toContain('session_id=session-a');
});

test('output lands in the terminal', () => {
  open();
  act(() => sockets[0].emit({ type: 'output', data: 'hello\r\n' }));

  expect(terminals[0].written).toEqual(['hello\r\n']);
});

test('a malformed frame is ignored rather than crashing the tab', () => {
  open();
  act(() => sockets[0].onmessage?.({ data: 'not json' }));

  expect(terminals[0].written).toEqual([]);
});

test('typing goes to the socket, not into the page', () => {
  open();
  act(() => terminals[0].type('ls\r'));

  expect(sockets[0].sent).toContain(JSON.stringify({ type: 'input', data: 'ls\r' }));
});

test('a closed socket swallows the keystroke instead of throwing', () => {
  open();
  sockets[0].readyState = FakeSocket.CLOSED;
  act(() => terminals[0].type('ls\r'));

  expect(sockets[0].sent).toEqual([]);
});

test('an exit reports its code, and the close that follows does not overwrite it', () => {
  // The socket always closes after the process exits; without the guard the
  // banner flipped from "exited (0)" to a generic "connection closed".
  const onExit = vi.fn();
  open({ onExit });

  act(() => sockets[0].emit({ type: 'exit', code: 0 }));
  act(() => sockets[0].onclose?.({ reason: '' }));

  expect(onExit).toHaveBeenCalledWith(0);
  expect(screen.getByRole('status')).toHaveTextContent('0');
  expect(screen.getByRole('status')).not.toHaveTextContent('Connection closed');
});

test('a socket closing on its own says so and offers a fresh session', () => {
  open();
  act(() => sockets[0].onclose?.({ reason: '' }));

  expect(screen.getByRole('status')).toHaveTextContent('Connection closed');
  expect(screen.getByRole('button', { name: 'Start new' })).toBeInTheDocument();
});

test('the server’s own reason wins over the generic message', () => {
  open();
  act(() => sockets[0].onclose?.({ reason: 'Workspace is not registered' }));

  expect(screen.getByRole('status')).toHaveTextContent('Workspace is not registered');
});

test('restarting opens a new socket rather than reattaching to the old one', () => {
  // The endpoint spawns a process per connection and issues its own id, so
  // there is nothing to reconnect *to* -- a silent reconnect would hand back a
  // different shell wearing the old one's scrollback.
  open();
  act(() => sockets[0].onclose?.({ reason: '' }));

  fireEvent.click(screen.getByRole('button', { name: 'Start new' }));

  expect(sockets).toHaveLength(2);
  expect(sockets[0].closed).toBe(true);
  expect(terminals[0].disposed).toBe(true);
});

test('a torn-down socket cannot post its close over a live terminal', () => {
  const { rerender } = open();
  const stale = sockets[0];
  rerender(<BrowserTerminal engine="codex" cwd="/workspace/project-a" />);

  act(() => stale.onclose?.({ reason: 'gone' }));

  expect(screen.queryByRole('status')).not.toBeInTheDocument();
});

test('clear wipes the buffer and puts the caret back in the shell', () => {
  open();

  fireEvent.click(screen.getByRole('button', { name: 'Clear the terminal' }));

  expect(terminals[0].cleared).toBe(1);
  expect(terminals[0].focused).toBeGreaterThan(0);
});

test('copy hands the whole scrollback to the clipboard', async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
  open();

  fireEvent.click(screen.getByRole('button', { name: 'Copy everything on screen' }));

  expect(writeText).toHaveBeenCalledWith('scrollback text');
});

test('a denied clipboard is the user’s answer, not a banner over the terminal', async () => {
  const writeText = vi.fn().mockRejectedValue(new Error('denied'));
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
  open();

  fireEvent.click(screen.getByRole('button', { name: 'Copy everything on screen' }));
  await act(async () => {});

  expect(screen.queryByRole('status')).not.toBeInTheDocument();
});

test('unmounting closes the socket and disposes the terminal', () => {
  const { unmount } = open();

  unmount();

  expect(sockets[0].closed).toBe(true);
  expect(terminals[0].disposed).toBe(true);
});

test('when document.hidden is true and waiting_input received, updates title with 🔴, calls desktop notification and onTerminalEvent', () => {
  const onTerminalEvent = vi.fn();
  open({ onTerminalEvent });

  setDocumentHidden(true);

  act(() => {
    sockets[0].emit({ type: 'output', data: 'Do you want to proceed? [y/N]' });
  });

  expect(onTerminalEvent).toHaveBeenCalledWith('waiting_input', 'Do you want to proceed? [y/N]');
  expect(document.title).toContain('🔴');
  expect(document.title).toContain('[claude] Waiting for input...');
  expect(mockNotificationConstructor).toHaveBeenCalledWith(
    expect.stringContaining('🔴 [claude] Waiting for input...'),
    expect.objectContaining({ body: 'Do you want to proceed? [y/N]' }),
  );
});

test('when visibilitychange fires with hidden=false, restores previous document title', () => {
  open();
  setDocumentHidden(true);

  act(() => {
    sockets[0].emit({ type: 'output', data: 'Do you want to proceed? [y/N]' });
  });
  expect(document.title).toContain('🔴');

  setDocumentHidden(false);
  act(() => {
    document.dispatchEvent(new Event('visibilitychange'));
  });

  expect(document.title).toBe('CodeAgent Test');
});

test('when user types into terminal, restores previous document title', () => {
  open();
  setDocumentHidden(true);

  act(() => {
    sockets[0].emit({ type: 'output', data: 'Do you want to proceed? [y/N]' });
  });
  expect(document.title).toContain('🔴');

  act(() => {
    terminals[0].type('y\r');
  });

  expect(document.title).toBe('CodeAgent Test');
});

test('when window focus event fires, restores previous document title', () => {
  open();
  setDocumentHidden(true);

  act(() => {
    sockets[0].emit({ type: 'output', data: 'Do you want to proceed? [y/N]' });
  });
  expect(document.title).toContain('🔴');

  act(() => {
    window.dispatchEvent(new Event('focus'));
  });

  expect(document.title).toBe('CodeAgent Test');
});

test('clicking desktop notification focuses window and terminal and restores title', () => {
  const focusSpy = vi.spyOn(window, 'focus').mockImplementation(() => {});
  open();
  setDocumentHidden(true);

  act(() => {
    sockets[0].emit({ type: 'output', data: 'Do you want to proceed? [y/N]' });
  });
  expect(mockNotificationInstances.length).toBe(1);
  const notif = mockNotificationInstances[0];

  const mockEv = { preventDefault: vi.fn() };
  act(() => {
    notif.onclick?.(mockEv as unknown as Event);
  });

  expect(focusSpy).toHaveBeenCalled();
  expect(terminals[0].focused).toBeGreaterThan(0);
  expect(document.title).toBe('CodeAgent Test');
});

test('detects completed event and updates title with 🟢 when hidden', () => {
  const onTerminalEvent = vi.fn();
  open({ onTerminalEvent });
  setDocumentHidden(true);

  act(() => {
    sockets[0].emit({ type: 'output', data: 'Task completed in 3.5s\r\n' });
  });

  expect(onTerminalEvent).toHaveBeenCalledWith('completed', 'Task completed in 3.5s\r\n');
  expect(document.title).toContain('🟢');
  expect(document.title).toContain('[claude] Task completed');
});

test('detects rate_limit event and updates title with ⚠️ when hidden', () => {
  const onTerminalEvent = vi.fn();
  open({ onTerminalEvent });
  setDocumentHidden(true);

  act(() => {
    sockets[0].emit({ type: 'output', data: 'HTTP 429 Too Many Requests\r\n' });
  });

  expect(onTerminalEvent).toHaveBeenCalledWith('rate_limit', 'HTTP 429 Too Many Requests\r\n');
  expect(document.title).toContain('⚠️');
  expect(document.title).toContain('[claude] Rate limit / Quota exceeded');
});

test('when document is visible, triggers onTerminalEvent but does not change title or send desktop notification', () => {
  const onTerminalEvent = vi.fn();
  open({ onTerminalEvent });
  setDocumentHidden(false);

  act(() => {
    sockets[0].emit({ type: 'output', data: 'Do you want to proceed? [y/N]' });
  });

  expect(onTerminalEvent).toHaveBeenCalledWith('waiting_input', 'Do you want to proceed? [y/N]');
  expect(document.title).toBe('CodeAgent Test');
  expect(mockNotificationConstructor).not.toHaveBeenCalled();
});

test('unmounting restores original title if modified', () => {
  const { unmount } = open();
  setDocumentHidden(true);

  act(() => {
    sockets[0].emit({ type: 'output', data: 'Do you want to proceed? [y/N]' });
  });
  expect(document.title).toContain('🔴');

  unmount();
  expect(document.title).toBe('CodeAgent Test');
});

