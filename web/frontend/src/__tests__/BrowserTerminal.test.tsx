import { act, fireEvent, render, screen } from '@testing-library/react';
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

beforeEach(async () => {
  terminals.length = 0;
  sockets.length = 0;
  globalThis.WebSocket = FakeSocket as unknown as typeof WebSocket;
  globalThis.ResizeObserver = class {
    observe() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
  BrowserTerminal = (await import('../components/BrowserTerminal')).default;
});

afterEach(() => {
  globalThis.WebSocket = originalWebSocket;
});

function open(props: Partial<{ engine: string; cwd: string; sessionId?: string; onExit: (code: number | null) => void }> = {}) {
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
