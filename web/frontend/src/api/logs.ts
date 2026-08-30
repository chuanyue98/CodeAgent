import { useState, useEffect } from 'react';
import request from '../utils/request';
import { withToken } from '../utils/token';

export interface LogFile {
  taskId: string;
  name: string;
  size: number;
  modified: number;
}

export interface LogFileContent {
  taskId: string;
  content: string;
}

export async function fetchLogFiles(): Promise<LogFile[]> {
  return request('/api/logs/files');
}

export async function fetchLogFile(taskId: string): Promise<LogFileContent> {
  return request(`/api/logs/${encodeURIComponent(taskId)}`);
}

export function useLogStream(taskId: string | null) {
  const [lines, setLines] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [finished, setFinished] = useState<string | null>(null);

  useEffect(() => {
    if (!taskId) return;

    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLines([]);
    setError(null);
    setConnected(false);
    setFinished(null);

    // EventSource cannot set headers, so the token rides the query string.
    const url = withToken(`/api/logs/${encodeURIComponent(taskId)}/stream`);
    const eventSource = new EventSource(url);

    eventSource.onopen = () => { setConnected(true); setError(null); };
    eventSource.onerror = () => {
      setConnected(false);
      setError('Connection lost. Retrying...');
    };

    // The server ends the stream once the run stops. EventSource treats a
    // closed connection as a dropped one and reconnects on its own, so the
    // close has to be explicit here or a finished run reconnects forever
    // behind a "Connection lost" banner.
    eventSource.addEventListener('done', (event: MessageEvent) => {
      try {
        setFinished(JSON.parse(event.data).status ?? 'completed');
      } catch {
        setFinished('completed');
      }
      setConnected(false);
      setError(null);
      eventSource.close();
    });

    eventSource.addEventListener('message', (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        if (data.content) {
          setLines(prev => {
            const newLines = data.content.split('\n').filter((l: string) => l.trim());
            const MAX_LINES = 10000;
            const trimmed = [...prev, ...newLines];
            return trimmed.length > MAX_LINES ? trimmed.slice(trimmed.length - MAX_LINES) : trimmed;
          });
        }
        if (data.error) {
          setError(data.error);
          eventSource.close();
        }
      } catch {
        // ignore parse errors
      }
    });

    return () => {
      eventSource.close();
      setConnected(false);
    };
  }, [taskId]);

  return { lines, error, connected, finished };
}
