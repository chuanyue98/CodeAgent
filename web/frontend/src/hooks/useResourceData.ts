import { useState, useEffect, useCallback } from 'react';
import request from '../utils/request';

interface ResourceDataResult<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

/**
 * Shared hook for fetching resource data (skills, plugins, hooks, prompts).
 * Provides loading/error states and a refetch callback for error recovery
 * without page reload.
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
    let mounted = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    setError(null);

    request<T>(endpoint)
      .then((result) => {
        if (!mounted) return;
        setData(result);
      })
      .catch((err: unknown) => {
        if (!mounted) return;
        setError(err instanceof Error ? err.message : 'Failed to fetch data');
      })
      .finally(() => {
        if (!mounted) return;
        setLoading(false);
      });

    return () => {
      mounted = false;
    };
  }, [endpoint, nonce]);

  return { data, loading, error, refetch };
}

export default useResourceData;
