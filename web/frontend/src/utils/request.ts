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
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...restConfig.headers,
      },
      ...restConfig,
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      throw new Error(`Request failed with status ${response.status}`);
    }

    const data = await response.json() as ApiResponse<T>;
    return data.data;
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      throw new Error('Request timeout', { cause: error });
    }
    console.error('Request error:', error);
    throw error;
  }
}

export default request;
