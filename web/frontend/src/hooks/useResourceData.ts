import { useQuery } from '@tanstack/react-query';
import request from '../utils/request';
import { queryClient as defaultQueryClient } from '../utils/queryClient';

interface ResourceDataResult<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

/**
 * Shared hook for fetching resource data (skills, plugins, hooks, prompts).
 * Backed by TanStack Query for caching, automatic deduplication, and
 * safe abort on unmount/endpoint change.
 */
function useResourceData<T>(endpoint: string): ResourceDataResult<T> {
  const { data, isLoading, isError, error, refetch } = useQuery<T>(
    {
      queryKey: [endpoint],
      queryFn: ({ signal }) => request<T>(endpoint, { signal }),
    },
    defaultQueryClient,
  );

  return {
    data: data ?? null,
    loading: isLoading,
    error: isError ? (error instanceof Error ? error.message : 'Failed to fetch data') : null,
    refetch: () => {
      void refetch();
    },
  };
}

export default useResourceData;
