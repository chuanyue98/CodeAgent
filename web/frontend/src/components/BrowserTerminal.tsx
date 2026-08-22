import { useEffect, useRef, useState } from 'react';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';
import { ptyWebSocketUrl } from '../api/pty';

type ConnectionState = 'connecting' | 'open' | 'closed' | 'error';

interface BrowserTerminalProps {
  engine: string;
  cwd: string;
  onExit?: (code: number | null) => void;
}

export default function BrowserTerminal({ engine, cwd, onExit }: BrowserTerminalProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [state, setState] = useState<ConnectionState>('connecting');
  const [message, setMessage] = useState<string | null>(null);
  const onExitRef = useRef(onExit);
  useEffect(() => {
    onExitRef.current = onExit;
  }, [onExit]);

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

    setState('connecting');
    setMessage(null);
    let exitHandled = false;
    const socket = new WebSocket(ptyWebSocketUrl(engine, cwd));

    socket.onopen = () => {
      setState('open');
      fit.fit();
      socket.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }));
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
        setMessage(`Session ended (exit code ${payload.code ?? 'unknown'})`);
        onExitRef.current?.(typeof payload.code === 'number' ? payload.code : null);
      }
    };
    socket.onerror = () => {
      setState('error');
      setMessage('Terminal connection error');
    };
    socket.onclose = (event) => {
      if (exitHandled) return;
      setState('closed');
      setMessage(event.reason || 'Connection closed');
    };

    const dataDisposable = term.onData((data) => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'input', data }));
      }
    });

    const resizeObserver = new ResizeObserver(() => {
      fit.fit();
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }));
      }
    });
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      dataDisposable.dispose();
      socket.close();
      term.dispose();
    };
  }, [engine, cwd]);

  return (
    <div className="flex h-full min-h-0 flex-col space-y-2">
      {message && (
        <div
          role="status"
          className={`rounded-lg px-3 py-2 text-xs ${
            state === 'error'
              ? 'border border-red-200 bg-red-50 text-red-700'
              : 'border border-slate-200 bg-slate-50 text-slate-600'
          }`}
        >
          {message}
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
