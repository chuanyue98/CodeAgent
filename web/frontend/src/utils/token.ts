/**
 * Local UI token handling.
 *
 * The backend requires a per-install token on every `/api` call (see
 * core/web/security.py). `ca ui` opens the browser at `/?ca_token=<token>`;
 * this module lifts that value into sessionStorage on boot and scrubs it
 * from the address bar, so the secret does not linger in the URL, in
 * browser history, or in a `Referer` header on any outbound link.
 *
 * sessionStorage rather than localStorage: the token is per-install, not
 * per-user, and scoping it to the tab means closing the tab drops it. A
 * reopened UI gets a fresh copy from the launcher anyway.
 */

const STORAGE_KEY = 'codeagent.uiToken';
export const TOKEN_QUERY_PARAM = 'ca_token';
export const TOKEN_HEADER = 'X-CA-Token';

let cached: string | null = null;

/**
 * Reads a token out of the current URL into sessionStorage, then removes
 * it from the visible location. Call once, before the first API request.
 */
export function bootstrapToken(): void {
  try {
    const url = new URL(window.location.href);
    const fromUrl = url.searchParams.get(TOKEN_QUERY_PARAM);
    if (!fromUrl) return;

    sessionStorage.setItem(STORAGE_KEY, fromUrl);
    cached = fromUrl;

    url.searchParams.delete(TOKEN_QUERY_PARAM);
    // replaceState, not assign: rewriting the address bar must not reload
    // the app (which would drop the token we just captured) and must not
    // push a history entry the Back button could return to.
    window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);
  } catch {
    // Malformed URL or storage denied (private mode, embedded webview).
    // Requests will 401 and surface a real error rather than failing here.
  }
}

export function getToken(): string | null {
  if (cached !== null) return cached;
  try {
    cached = sessionStorage.getItem(STORAGE_KEY);
  } catch {
    cached = null;
  }
  return cached;
}

/** Header map to merge into a fetch() call. Empty when no token is known. */
export function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { [TOKEN_HEADER]: token } : {};
}

/**
 * Appends the token to a URL's query string.
 *
 * Needed for the two transports that cannot carry a request header:
 * `EventSource` (the log and chat streams) and `WebSocket` (the agent
 * event stream and the PTY). Everything else should use `authHeaders()`.
 */
export function withToken(url: string): string {
  const token = getToken();
  if (!token) return url;
  const separator = url.includes('?') ? '&' : '?';
  return `${url}${separator}${TOKEN_QUERY_PARAM}=${encodeURIComponent(token)}`;
}
