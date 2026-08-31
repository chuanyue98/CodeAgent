import { useCallback, useEffect, useRef, useState } from 'react';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';
import { ClipboardCopy, Eraser, RotateCw } from 'lucide-react';
import { ptyWebSocketUrl } from '../api/pty';
import { useT } from '../i18n/context';

type ConnectionState = 'connecting' | 'open' | 'closed' | 'error';

interface BrowserTerminalProps {
  engine: string;
  cwd: string;
  /** Resume this session rather than starting a fresh one. */
  sessionId?: string;
  /** Attach to a live browser terminal by its /api/pty/sessions id. */
  attachId?: string;
  onExit?: (code: number | null) => void;
}

/** Coalesces the burst of resize events a drag produces into one fit. */
const RESIZE_DEBOUNCE_MS = 100;

export default function BrowserTerminal({
  engine,
  cwd,
  sessionId,
  attachId,
  onExit,
}: BrowserTerminalProps) {
  const t = useT();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const termRef = useRef<Terminal | null>(null);
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
  // `t` changes identity when the language does. Held in the effect's deps it
  // tore the socket down and spawned a *new* PTY on every language switch,
  // which with several terminals open would kill all of them at once.
  const tRef = useRef(t);
  useEffect(() => {
    tRef.current = t;
  }, [t]);

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
    termRef.current = term;

    /** True when the fit actually happened; a hidden tab measures 0x0. */
    const fitIfVisible = (): boolean => {
      if (!container.clientWidth || !container.clientHeight) return false;
      fit.fit();
      return true;
    };
    const isVisible = () => container.clientWidth > 0 && container.clientHeight > 0;

    fitIfVisible();
    // Without this the caret is in the page, not the shell: opening a
    // terminal and typing sent the keystrokes nowhere until you clicked it.
    // Only for the tab actually on screen -- a background tab whose socket
    // opens later must not steal the caret out of the one being typed in.
    if (isVisible()) term.focus();

    setState('connecting');
    setMessage(null);
    let exitHandled = false;
    // A socket this effect has torn down still fires `onclose` afterwards, and
    // by then a later run owns the state -- its "connection closed" would sit
    // over a terminal that is connected and typing fine.
    let superseded = false;
    const socket = new WebSocket(ptyWebSocketUrl(engine, cwd, sessionId, attachId));

    const sendResize = () => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }));
      }
    };

    socket.onopen = () => {
      if (superseded) return;
      setState('open');
      setMessage(null);
      if (fitIfVisible()) sendResize();
      if (isVisible()) term.focus();
    };
    socket.onmessage = (event) => {
      if (superseded) return;
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
        setMessage(tRef.current('terminal.sessionEnded', { code: String(payload.code ?? 'unknown') }));
        onExitRef.current?.(typeof payload.code === 'number' ? payload.code : null);
      }
    };
    socket.onerror = () => {
      if (superseded) return;
      setState('error');
      setMessage(tRef.current('terminal.connectionError'));
    };
    socket.onclose = (event) => {
      if (superseded || exitHandled) return;
      setState('closed');
      setMessage(event.reason || tRef.current('terminal.connectionClosed'));
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
        // Hiding a tab fires this at 0x0; showing it again fires it with the
        // real box, which is what re-fits the buffer.
        if (fitIfVisible()) sendResize();
      }, RESIZE_DEBOUNCE_MS);
    });
    resizeObserver.observe(container);

    return () => {
      superseded = true;
      clearTimeout(resizeTimer);
      resizeObserver.disconnect();
      dataDisposable.dispose();
      socket.close();
      termRef.current = null;
      term.dispose();
    };
  }, [engine, cwd, sessionId, attachId, attempt]);

  const canRestart = state === 'closed' || state === 'error';

  const clear = useCallback(() => {
    termRef.current?.clear();
    termRef.current?.focus();
  }, []);

  const copyAll = useCallback(() => {
    const term = termRef.current;
    if (!term) return;
    term.selectAll();
    const text = term.getSelection();
    term.clearSelection();
    // Denied clipboard permission is the user's answer, not an error worth a
    // banner over the terminal.
    void navigator.clipboard?.writeText(text).catch(() => {});
    term.focus();
  }, []);

  return (
    <div className="flex h-full min-h-0 flex-col space-y-2">
      {message && (
        <div
          role="status"
          className={`flex flex-wrap items-center justify-between gap-2 rounded-lg px-3 py-2 text-xs ${
            state === 'error'
              ? 'border border-destructive/30 bg-destructive/10 text-destructive'
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
      <div className="flex shrink-0 items-center justify-end gap-1">
        <button
          onClick={clear}
          aria-label={t('terminal.clear')}
          title={t('terminal.clear')}
          className="rounded-md p-1 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
        >
          <Eraser className="h-3.5 w-3.5" />
        </button>
        <button
          onClick={copyAll}
          aria-label={t('terminal.copyAll')}
          title={t('terminal.copyAll')}
          className="rounded-md p-1 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
        >
          <ClipboardCopy className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Fills the page's remaining height instead of a fixed vh slice -- the
          FitAddon + ResizeObserver below re-fit whenever this box resizes. */}
      <div
        ref={containerRef}
        className="min-h-56 w-full flex-1 overflow-hidden rounded-xl border border-slate-200 bg-[#0f172a] p-2"
      />
    </div>
  );
}
