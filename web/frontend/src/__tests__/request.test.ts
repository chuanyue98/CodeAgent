import { afterEach, expect, test, vi } from 'vitest';
import request from '../utils/request';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

test.each([200, 500])('收到 %s 响应头后仍限制响应体读取时间', async status => {
  vi.useFakeTimers();
  vi.stubGlobal('fetch', vi.fn(async (_url, config: RequestInit) => {
    const read = () => new Promise<string>((_resolve, reject) => {
      config.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
    });
    return { ok: status === 200, status, text: read, json: read };
  }));
  const result = expect(request('/test', { timeout: 100 })).rejects.toThrow('Request timeout');
  await vi.advanceTimersByTimeAsync(100);
  await result;
});

test.each([new Headers({ 'X-Test': 'value' }), [['X-Test', 'value']] as [string, string][]])(
  '支持 RequestInit 的所有请求头形式', async headers => {
    const fetchMock = vi.fn(async () => ({ ok: true, text: async () => '{}' }));
    vi.stubGlobal('fetch', fetchMock);
    await request('/test', { headers });
    const options = (fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(new Headers(options.headers).get('X-Test')).toBe('value');
  },
);

test('204 No Content 响应返回 undefined 而非抛出空响应异常', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 204, text: async () => '' })));
  await expect(request<void>('/test', { method: 'DELETE' })).resolves.toBeUndefined();
});

test('解析 FastAPI 422 校验错误数组 detail', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: false,
    status: 422,
    json: async () => ({ detail: [{ msg: 'Field required' }, { msg: 'Must be positive' }] }),
  })));
  await expect(request('/test')).rejects.toThrow('Field required; Must be positive');
});
