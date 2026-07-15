import { useState, useEffect } from 'react';
import request from '../utils/request';

export interface LogFile {
  task_id: string;
  name: string;
  size: number;
  modified: number;
}

export interface LogFileContent {
  task_id: string;
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

  useEffect(() => {
    if (!taskId) return;

    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLines([]);
    setError(null);
    setConnected(false);

    const url = `/api/logs/${encodeURIComponent(taskId)}/stream`;
    const eventSource = new EventSource(url);

    eventSource.onopen = () => { setConnected(true); setError(null); };
    eventSource.onerror = () => {
      setConnected(false);
      setError('Connection lost. Retrying...');
    };

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

  return { lines, error, connected };
}
