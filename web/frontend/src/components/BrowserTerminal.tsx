import { useCallback, useEffect, useRef, useState } from 'react';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';
import { RotateCw } from 'lucide-react';
import { ptyWebSocketUrl } from '../api/pty';
import { useT } from '../i18n/context';

type ConnectionState = 'connecting' | 'open' | 'closed' | 'error';

interface BrowserTerminalProps {
  engine: string;
  cwd: string;
  onExit?: (code: number | null) => void;
}

/** Coalesces the burst of resize events a drag produces into one fit. */
const RESIZE_DEBOUNCE_MS = 100;

export default function BrowserTerminal({ engine, cwd, onExit }: BrowserTerminalProps) {
  const t = useT();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [state, setState] = useState<ConnectionState>('connecting');
  const [message, setMessage] = useState<string | null>(null);
  // Bumping this tears the effect down and starts a fresh session. The PTY
  // endpoint spawns a process per connection and issues its own session id,
  // so there is nothing to reconnect *to* -- reconnecting silently would hand
  // back a different shell wearing the old one's scrollback. Until the server
  // keeps sessions alive across sockets, this stays a deliberate button that
  // says what it does.
  const [attempt, setAttempt] = useState(0);
  const onExitRef = useRef(onExit);
  useEffect(() => {
    onExitRef.current = onExit;
  }, [onExit]);

  const restart = useCallback(() => setAttempt(previous => previous + 1), []);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const term = new Terminal({
      cursorBlink: true,
      convertEol: true,
      fontSize: 13,
      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
      theme: { background: '#0f172a' },
      screenReaderMode: true,
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(container);
    fit.fit();
    // Without this the caret is in the page, not the shell: opening a
    // terminal and typing sent the keystrokes nowhere until you clicked it.
    term.focus();

    setState('connecting');
    setMessage(null);
    let exitHandled = false;
    const socket = new WebSocket(ptyWebSocketUrl(engine, cwd));

    const sendResize = () => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }));
      }
    };

    socket.onopen = () => {
      setState('open');
      fit.fit();
      sendResize();
      term.focus();
    };
    socket.onmessage = (event) => {
      let payload: { type?: string; data?: string; code?: number };
      try {
        payload = JSON.parse(event.data);
      } catch {
        return;
      }
      if (payload.type === 'output' && typeof payload.data === 'string') {
        term.write(payload.data);
      } else if (payload.type === 'exit') {
        exitHandled = true;
        setState('closed');
        setMessage(t('terminal.sessionEnded', { code: String(payload.code ?? 'unknown') }));
        onExitRef.current?.(typeof payload.code === 'number' ? payload.code : null);
      }
    };
    socket.onerror = () => {
      setState('error');
      setMessage(t('terminal.connectionError'));
    };
    socket.onclose = (event) => {
      if (exitHandled) return;
      setState('closed');
      setMessage(event.reason || t('terminal.connectionClosed'));
    };

    const dataDisposable = term.onData((data) => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'input', data }));
      }
    });

    // A drag fires ResizeObserver on nearly every frame, and each callback
    // re-flowed the whole buffer and put a resize on the wire. Fit once the
    // drag settles instead.
    let resizeTimer: ReturnType<typeof setTimeout> | undefined;
    const resizeObserver = new ResizeObserver(() => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => {
        fit.fit();
        sendResize();
      }, RESIZE_DEBOUNCE_MS);
    });
    resizeObserver.observe(container);

    return () => {
      clearTimeout(resizeTimer);
      resizeObserver.disconnect();
      dataDisposable.dispose();
      socket.close();
      term.dispose();
    };
  }, [engine, cwd, attempt, t]);

  const canRestart = state === 'closed' || state === 'error';

  return (
    <div className="flex h-full min-h-0 flex-col space-y-2">
      {message && (
        <div
          role="status"
          className={`flex flex-wrap items-center justify-between gap-2 rounded-lg px-3 py-2 text-xs ${
            state === 'error'
              ? 'border border-red-200 bg-red-50 text-red-700'
              : 'border border-slate-200 bg-slate-50 text-slate-600'
          }`}
        >
          <span className="min-w-0">{message}</span>
          {canRestart && (
            <button
              onClick={restart}
              title={t('terminal.startNewHint')}
              className="flex shrink-0 items-center gap-1 rounded-md border border-slate-300 bg-white px-2 py-1 font-medium text-slate-600 transition-colors hover:bg-slate-50"
            >
              <RotateCw className="h-3 w-3" />
              {t('terminal.startNew')}
            </button>
          )}
        </div>
      )}
      {/* Fills the page's remaining height instead of a fixed vh slice -- the
          FitAddon + ResizeObserver below re-fit whenever this box resizes. */}
      <div
        ref={containerRef}
        className="min-h-56 w-full flex-1 overflow-hidden rounded-xl border border-slate-200 bg-[#0f172a] p-2"
      />
    </div>
  );
}
