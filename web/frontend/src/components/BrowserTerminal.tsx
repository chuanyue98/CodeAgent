import { useCallback, useEffect, useRef, useState } from 'react';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';
import { RotateCw } from 'lucide-react';
import { ptyWebSocketUrl } from '../api/pty';
import { useT } from '../i18n/context';
import { detectTerminalEvent, stripAnsi } from '../utils/terminalDetector';
import type { TerminalEventType } from '../utils/terminalDetector';
import { requestNotificationPermission, sendDesktopNotification } from '../utils/desktopNotification';

type ConnectionState = 'connecting' | 'open' | 'closed' | 'error';

export interface BrowserTerminalProps {
  engine: string;
  cwd: string;
  /** Resume this session rather than starting a fresh one. */
  sessionId?: string;
  /** Attach to a live browser terminal by its /api/pty/sessions id. */
  attachId?: string;
  fontSize?: number;
  copyOnSelect?: boolean;
  onExit?: (code: number | null) => void;
  onTerminalEvent?: (event: TerminalEventType, chunk: string) => void;
}

function getAlertTitle(event: TerminalEventType, engine: string): string {
  switch (event) {
    case 'waiting_input':
      return `🔴 [${engine}] Waiting for input...`;
    case 'completed':
      return `🟢 [${engine}] Task completed`;
    case 'rate_limit':
      return `⚠️ [${engine}] Rate limit / Quota exceeded`;
  }
}

function getNotificationBody(event: TerminalEventType, chunk: string): string {
  const clean = stripAnsi(chunk).trim();
  if (clean.length > 0 && clean.length <= 120) {
    return clean;
  }
  switch (event) {
    case 'waiting_input':
      return 'Terminal process is waiting for user input.';
    case 'completed':
      return 'Task completed.';
    case 'rate_limit':
      return 'Rate limit or quota exceeded.';
  }
}

/** Coalesces the burst of resize events a drag produces into one fit. */
const RESIZE_DEBOUNCE_MS = 100;

export default function BrowserTerminal({
  engine,
  cwd,
  sessionId,
  attachId,
  fontSize = 13,
  copyOnSelect = true,
  onExit,
  onTerminalEvent,
}: BrowserTerminalProps) {
  const t = useT();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const termRef = useRef<Terminal | null>(null);
  const fitRef = useRef<FitAddon | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const [copiedToast, setCopiedToast] = useState(false);
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
  const onTerminalEventRef = useRef(onTerminalEvent);
  useEffect(() => {
    onTerminalEventRef.current = onTerminalEvent;
  }, [onTerminalEvent]);

  // Request notification permission non-blockingly on mount
  useEffect(() => {
    void requestNotificationPermission();
  }, []);

  const originalTitleRef = useRef<string | null>(null);

  const restoreTitle = useCallback(() => {
    if (typeof document !== 'undefined' && originalTitleRef.current !== null) {
      document.title = originalTitleRef.current;
      originalTitleRef.current = null;
    }
  }, []);

  const requestPermissionOnInteraction = useCallback(() => {
    if (typeof Notification !== 'undefined' && Notification.permission === 'default') {
      void requestNotificationPermission();
    }
  }, []);

  // `t` changes identity when the language does. Held in the effect's deps it
  // tore the socket down and spawned a *new* PTY on every language switch,
  // which with several terminals open would kill all of them at once.
  const tRef = useRef(t);
  useEffect(() => {
    tRef.current = t;
  }, [t]);

  const restart = useCallback(() => setAttempt(previous => previous + 1), []);

  // Dynamic font size update without reconnecting socket
  useEffect(() => {
    if (termRef.current && fontSize) {
      if (termRef.current.options && termRef.current.options.fontSize !== fontSize) {
        termRef.current.options.fontSize = fontSize;
      }
      if (containerRef.current?.clientWidth && containerRef.current?.clientHeight) {
        fitRef.current?.fit();
        if (socketRef.current?.readyState === WebSocket.OPEN && termRef.current) {
          socketRef.current.send(
            JSON.stringify({
              type: 'resize',
              cols: termRef.current.cols,
              rows: termRef.current.rows,
            })
          );
        }
      }
    }
  }, [fontSize]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const term = new Terminal({
      cursorBlink: true,
      convertEol: true,
      fontSize: fontSize || 13,
      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
      theme: { background: '#0f172a' },
      screenReaderMode: true,
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(container);
    termRef.current = term;
    fitRef.current = fit;

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
    socketRef.current = socket;

    const handleVisibilityChange = () => {
      if (typeof document !== 'undefined' && !document.hidden) {
        restoreTitle();
      }
    };
    const handleWindowFocus = () => {
      restoreTitle();
    };

    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', handleVisibilityChange);
    }
    if (typeof window !== 'undefined') {
      window.addEventListener('focus', handleWindowFocus);
    }

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

        const chunk = payload.data;
        const detected = detectTerminalEvent(chunk);
        if (detected) {
          onTerminalEventRef.current?.(detected, chunk);
          if (typeof document !== 'undefined' && document.hidden) {
            if (originalTitleRef.current === null) {
              originalTitleRef.current = document.title;
            }
            const alertTitle = getAlertTitle(detected, engine);
            document.title = alertTitle;
            sendDesktopNotification(
              alertTitle,
              { body: getNotificationBody(detected, chunk) },
              () => {
                if (typeof window !== 'undefined') {
                  window.focus();
                }
                termRef.current?.focus();
                restoreTitle();
              },
            );
          }
        }
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
      restoreTitle();
      requestPermissionOnInteraction();
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'input', data }));
      }
    });

    let copyTimer: ReturnType<typeof setTimeout> | undefined;
    let selectionDisposable = { dispose: () => {} };
    if (typeof term.onSelectionChange === 'function') {
      selectionDisposable = term.onSelectionChange(() => {
        if (!copyOnSelect) return;
        clearTimeout(copyTimer);
        copyTimer = setTimeout(() => {
          const sel = term.getSelection();
          if (sel && sel.trim().length > 0) {
            if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
              void navigator.clipboard.writeText(sel).then(() => {
                setCopiedToast(true);
                setTimeout(() => setCopiedToast(false), 1500);
              }).catch(() => {});
            }
          }
        }, 250);
      });
    }

    if (typeof term.attachCustomKeyEventHandler === 'function') {
      term.attachCustomKeyEventHandler((e: KeyboardEvent) => {
      // 1. Ctrl+` bubbles to toggle terminal drawer
      if ((e.ctrlKey || e.metaKey) && e.key === '`') {
        return false;
      }
      // 2. Ctrl+C with text selected: copy text and avoid sending SIGINT \x03
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && (e.key === 'c' || e.key === 'C')) {
        if (term.hasSelection()) {
          const sel = term.getSelection();
          if (sel && typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
            void navigator.clipboard.writeText(sel).then(() => {
              setCopiedToast(true);
              setTimeout(() => setCopiedToast(false), 1500);
            }).catch(() => {});
          }
          term.clearSelection();
          return false;
        }
        return true;
      }
      // 3. Ctrl+Shift+C: copy text
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === 'c' || e.key === 'C')) {
        if (term.hasSelection()) {
          const sel = term.getSelection();
          if (sel && typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
            void navigator.clipboard.writeText(sel).then(() => {
              setCopiedToast(true);
              setTimeout(() => setCopiedToast(false), 1500);
            }).catch(() => {});
          }
          return false;
        }
      }
      // 4. Ctrl+Shift+V: paste from clipboard
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === 'v' || e.key === 'V')) {
        if (typeof navigator !== 'undefined' && navigator.clipboard?.readText && socket.readyState === WebSocket.OPEN) {
          void navigator.clipboard.readText().then((text) => {
            if (text) {
              socket.send(JSON.stringify({ type: 'input', data: text }));
            }
          }).catch(() => {});
          return false;
        }
      }
      // 5. Let Ctrl++/Ctrl+-/Ctrl+0 bubble to window for font zooming
      if ((e.ctrlKey || e.metaKey) && (e.key === '=' || e.key === '+' || e.key === '-' || e.key === '_' || e.key === '0')) {
        return false;
      }
      return true;
    });
    }

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
      restoreTitle();
      if (typeof document !== 'undefined') {
        document.removeEventListener('visibilitychange', handleVisibilityChange);
      }
      if (typeof window !== 'undefined') {
        window.removeEventListener('focus', handleWindowFocus);
      }
      superseded = true;
      clearTimeout(copyTimer);
      clearTimeout(resizeTimer);
      selectionDisposable.dispose();
      resizeObserver.disconnect();
      dataDisposable.dispose();
      socket.close();
      fitRef.current = null;
      socketRef.current = null;
      termRef.current = null;
      term.dispose();
    };
  }, [engine, cwd, sessionId, attachId, attempt, copyOnSelect, restoreTitle, requestPermissionOnInteraction]);

  const canRestart = state === 'closed' || state === 'error';

  return (
    <div
      className="relative flex h-full min-h-0 flex-col space-y-2"
      onClick={requestPermissionOnInteraction}
    >
      {copiedToast && (
        <div
          data-testid="terminal-copied-toast"
          className="pointer-events-none absolute right-4 top-3 z-30 flex items-center gap-1.5 rounded-lg border border-emerald-500/30 bg-emerald-950/90 px-3 py-1.5 text-xs font-medium text-emerald-300 shadow-lg backdrop-blur"
        >
          <span>✓</span>
          <span>{t('terminal.copiedToast')}</span>
        </div>
      )}
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

      {/* Fills the page's remaining height instead of a fixed vh slice -- the
          FitAddon + ResizeObserver below re-fit whenever this box resizes. */}
      <div
        ref={containerRef}
        className="min-h-56 w-full flex-1 overflow-hidden rounded-xl border border-slate-200 bg-[#0f172a] p-2"
      />
    </div>
  );
}
