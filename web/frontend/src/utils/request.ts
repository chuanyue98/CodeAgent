interface RequestConfig extends RequestInit {
  timeout?: number;
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

    const text = await response.text();
    if (!text) {
      return undefined as T;
    }

    return JSON.parse(text) as T;
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
