interface RequestConfig extends RequestInit {
  timeout?: number;
}

interface ApiResponse<T = unknown> {
  code: number;
  data: T;
  message: string;
}

const DEFAULT_TIMEOUT = 10000;

async function request<T = unknown>(url: string, config: RequestConfig = {}): Promise<T> {
  const { timeout = DEFAULT_TIMEOUT, ...restConfig } = config;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(url, {
      ...restConfig,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...(restConfig.headers as Record<string, string>),
      },
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      throw new Error(`Request failed with status ${response.status}`);
    }

    // 处理空响应的情况
    const text = await response.text();
    if (!text) {
      return undefined as T;
    }

    const data = JSON.parse(text) as unknown;

    // 验证响应结构
    if (
      typeof data === 'object' &&
      data !== null &&
      'data' in data
    ) {
      return (data as ApiResponse<T>).data;
    }

    // 如果不是标准结构，直接返回解析后的数据
    return data as T;
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      throw new Error('Request timeout', { cause: error });
    }
    if (error instanceof SyntaxError) {
      throw new Error('Invalid JSON response', { cause: error });
    }
    console.error('Request error:', error);
    throw error;
  }
}

export default request;
