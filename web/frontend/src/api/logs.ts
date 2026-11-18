import { useState, useEffect, useMemo } from 'react';
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
  cursor?: string;
}

export async function fetchLogFiles(): Promise<LogFile[]> {
  return request('/api/logs/files');
}

export async function fetchLogFile(taskId: string): Promise<LogFileContent> {
  return request(`/api/logs/${encodeURIComponent(taskId)}`);
}

export function useLogStream(taskId: string | null, snapshot: LogFileContent | null = null) {
  const [state, setState] = useState<{ taskId: string | null; content: string }>({ taskId: null, content: '' });
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [finished, setFinished] = useState<string | null>(null);

  useEffect(() => {
    if (!taskId || snapshot?.taskId !== taskId || !snapshot.cursor) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setState(previous =>
        previous.taskId === null && previous.content === '' ? previous : { taskId: null, content: '' },
      );
      setError(null);
      setConnected(false);
      setFinished(null);
      return;
    }
    let disposed = false;
    setState({ taskId, content: snapshot.content });
    setError(null);
    setConnected(false);
    setFinished(null);
    const url = withToken(`/api/logs/${encodeURIComponent(taskId)}/stream?cursor=${encodeURIComponent(snapshot.cursor)}`);
    const source = new EventSource(url);
    source.onopen = () => { if (!disposed) { setConnected(true); setError(null); } };
    // 浏览器使用 SSE 的 id 自动携带 Last-Event-ID，补发断线期间的内容。
    source.onerror = () => { if (!disposed) { setConnected(false); setError('Connection lost. Retrying...'); } };
    const receive = (event: MessageEvent, reset: boolean) => {
      if (disposed) return;
      try {
        const data = JSON.parse(event.data);
        if (data.error) {
          setError(data.error);
          setConnected(false);
          source.close();
          return;
        }
        if (typeof data.content === 'string') {
          setState(previous => {
            const text = reset ? data.content : previous.content + data.content;
            // 按文本拼接，不能把跨数据块的半行拆成两行。
            return { taskId, content: text.split('\n').slice(-10000).join('\n') };
          });
        }
      } catch { setError('Invalid log stream response'); }
    };
    source.addEventListener('message', (event: MessageEvent) => receive(event, false));
    source.addEventListener('reset', (event: MessageEvent) => receive(event, true));
    source.addEventListener('done', (event: MessageEvent) => {
      if (disposed) return;
      try {
        const data = JSON.parse(event.data);
        setFinished(typeof data?.status === 'string' ? data.status : 'completed');
      } catch {
        setFinished('completed');
      }
      setConnected(false);
      setError(null);
      source.close();
    });
    return () => { disposed = true; source.close(); };
  }, [taskId, snapshot]);

  const content = taskId && state.taskId === taskId ? state.content : undefined;
  const lines = useMemo(() => content?.split('\n') ?? [], [content]);
  return { lines, content, error, connected, finished };
}
