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
      let detail = `Request failed with status ${response.status}`;
      try {
        const body = await response.json() as { detail?: string | { error?: string; message?: string } };
        if (typeof body.detail === 'string') detail = body.detail;
        else if (body.detail?.error) detail = body.detail.error;
        else if (body.detail?.message) detail = body.detail.message;
      } catch {
        // Keep the status-based fallback when the response is not JSON.
      }
      throw new Error(detail);
    }

    const text = await response.text();
    if (!text) {
      throw new Error('Server returned an empty response body');
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
