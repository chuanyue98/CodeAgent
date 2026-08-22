import { useState, useEffect, useCallback } from 'react';
import request from '../utils/request';

interface ResourceDataResult<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

function isAbort(error: unknown): boolean {
  return error instanceof Error && error.name === 'AbortError';
}

/**
 * Shared hook for fetching resource data (skills, plugins, hooks, prompts).
 * Provides loading/error states and a refetch callback for error recovery
 * without page reload.
 *
 * In-flight requests are aborted on unmount and whenever `endpoint` changes
 * or `refetch` fires, so a slow response for an old endpoint can never
 * overwrite the data of the one now on screen.
 */
function useResourceData<T>(endpoint: string): ResourceDataResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  const refetch = useCallback(() => {
    setNonce((n) => n + 1);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    setError(null);

    request<T>(endpoint, { signal: controller.signal })
      .then((result) => {
        if (controller.signal.aborted) return;
        setData(result);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted || isAbort(err)) return;
        setError(err instanceof Error ? err.message : 'Failed to fetch data');
      })
      .finally(() => {
        // A superseded request must not clear the spinner its successor
        // just turned on.
        if (controller.signal.aborted) return;
        setLoading(false);
      });

    return () => controller.abort();
  }, [endpoint, nonce]);

  return { data, loading, error, refetch };
}

export default useResourceData;
