import { authHeaders } from './token';

interface RequestConfig extends RequestInit {
  timeout?: number;
}

const DEFAULT_TIMEOUT = 10000;

async function request<T = unknown>(url: string, config: RequestConfig = {}): Promise<T> {
  const { timeout = DEFAULT_TIMEOUT, ...restConfig } = config;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);
  // A caller-provided signal (e.g. a hook aborting a superseded request)
  // must be able to cancel the fetch even though the timeout owns the
  // controller that fetch listens to.
  const externalSignal = restConfig.signal;
  const onExternalAbort = () => controller.abort();
  if (externalSignal) {
    if (externalSignal.aborted) controller.abort();
    else externalSignal.addEventListener('abort', onExternalAbort, { once: true });
  }

  try {
    const headers = new Headers({ 'Content-Type': 'application/json', ...authHeaders() });
    new Headers(restConfig.headers).forEach((value, key) => headers.set(key, value));
    const response = await fetch(url, {
      ...restConfig,
      signal: controller.signal,
      headers,
    });

    if (!response.ok) {
      let detail = `Request failed with status ${response.status}`;
      if (response.status === 401) {
        // Reaching this means the server has the token check on, which only
        // happens when it is bound off loopback (or was told to). Naming the
        // recovery beats a generic "status 401" that sends people hunting
        // through backend logs -- and it has to be a recovery that works
        // whoever started the server, since "reopen with `ca ui`" is useless
        // when the process was launched some other way.
        throw new Error(
          'Not authorized: this server requires a UI token. Run `ca ui --show-token` ' +
            'to read it, then open this page as ?ca_token=<token>.',
        );
      }
      try {
        const body = await response.json() as {
          detail?: string | { error?: string; message?: string } | Array<{ msg?: string }>;
        };
        if (typeof body.detail === 'string') {
          detail = body.detail;
        } else if (Array.isArray(body.detail)) {
          const messages = body.detail
            .map(item => (item && typeof item.msg === 'string' ? item.msg : ''))
            .filter(Boolean);
          if (messages.length > 0) detail = messages.join('; ');
        } else if (body.detail?.error) {
          detail = body.detail.error;
        } else if (body.detail?.message) {
          detail = body.detail.message;
        }
      } catch {
        controller.signal.throwIfAborted();
        // Keep the status-based fallback when the response is not JSON.
      }
      throw new Error(detail);
    }

    if (response.status === 204 || response.status === 205) {
      return undefined as T;
    }

    const text = await response.text();
    if (!text) {
      throw new Error('Server returned an empty response body');
    }

    return JSON.parse(text) as T;
  } catch (error) {
    if (controller.signal.aborted) {
      // A caller-initiated abort is deliberate (request superseded or the
      // component unmounted); only the internal timeout deserves the
      // "Request timeout" message.
      if (externalSignal?.aborted) throw error;
      throw new Error('Request timeout', { cause: error });
    }
    if (error instanceof SyntaxError) {
      throw new Error('Invalid JSON response', { cause: error });
    }
    console.error('Request error:', error);
    throw error;
  } finally {
    clearTimeout(timeoutId);
    externalSignal?.removeEventListener('abort', onExternalAbort);
  }
}

export default request;
