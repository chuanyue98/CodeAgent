import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import { useLogStream } from '../api/logs';

class FakeSource {
  static instances: FakeSource[] = [];
  listeners = new Map<string, (event: MessageEvent) => void>();
  onopen?: () => void;
  onerror?: () => void;
  close = vi.fn();
  url: string;
  constructor(url: string) {
    this.url = url;
    FakeSource.instances.push(this);
  }
  addEventListener(name: string, handler: (event: MessageEvent) => void) { this.listeners.set(name, handler); }
  emit(name: string, data: unknown) { this.listeners.get(name)?.({ data: JSON.stringify(data) } as MessageEvent); }
}

afterEach(() => { vi.unstubAllGlobals(); FakeSource.instances = []; });

test('快照到达后才连接，按文本拼接半行，收到换代事件替换内容', async () => {
  vi.stubGlobal('EventSource', FakeSource);
  const snapshot = { taskId: 'test', content: 'first half', cursor: 'file:10:hash' };
  const { result, rerender, unmount } = renderHook(
    ({ ready }) => useLogStream('test', ready ? snapshot : null), { initialProps: { ready: false } },
  );
  expect(FakeSource.instances).toHaveLength(0);
  rerender({ ready: true });
  await waitFor(() => expect(FakeSource.instances).toHaveLength(1));
  const source = FakeSource.instances[0];
  expect(source.url).toContain('cursor=file%3A10%3Ahash');
  act(() => source.emit('message', { content: ' second half\n中文' }));
  expect(result.current.content).toBe('first half second half\n中文');
  act(() => source.emit('reset', { content: 'new file\n' }));
  expect(result.current.content).toBe('new file\n');
  act(() => source.emit('done', { status: 'completed' }));
  expect(result.current.finished).toBe('completed');
  expect(source.close).toHaveBeenCalled();
  unmount();
  act(() => source.emit('message', { content: 'stale' }));
  expect(result.current.content).toBe('new file\n');
});

test('handles malformed done payload and resets state when taskId clears', async () => {
  vi.stubGlobal('EventSource', FakeSource);
  const snapshot = { taskId: 'test', content: 'line 1', cursor: 'file:6:hash' };
  const { result, rerender } = renderHook(
    ({ taskId, ready }: { taskId: string | null; ready: boolean }) =>
      useLogStream(taskId, ready ? snapshot : null),
    { initialProps: { taskId: 'test' as string | null, ready: true } },
  );
  await waitFor(() => expect(FakeSource.instances).toHaveLength(1));
  const source = FakeSource.instances[0];
  act(() => {
    source.listeners.get('done')?.({ data: '{invalid-json' } as MessageEvent);
  });
  expect(result.current.finished).toBe('completed');
  rerender({ taskId: null, ready: false });
  expect(result.current.content).toBeUndefined();
  expect(result.current.finished).toBeNull();
});
