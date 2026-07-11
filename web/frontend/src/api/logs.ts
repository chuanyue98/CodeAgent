import { useState, useEffect } from 'react';

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
  const res = await fetch('/api/logs/files');
  if (!res.ok) throw new Error('Failed to fetch log files');
  return res.json();
}

export async function fetchLogFile(taskId: string): Promise<LogFileContent> {
  const res = await fetch(`/api/logs/${encodeURIComponent(taskId)}`);
  if (!res.ok) throw new Error('Failed to fetch log file');
  return res.json();
}

export function useLogStream(taskId: string | null) {
  const [lines, setLines] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!taskId) return;

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
            return [...prev, ...newLines];
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
