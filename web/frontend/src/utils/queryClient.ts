import { QueryClient } from '@tanstack/react-query';

/**
 * App-wide defaults mirror the pre-Query polling semantics: data refreshes
 * only on the intervals the pages set themselves. Focus-triggered refetches
 * would add endpoint traffic nobody asked for, and retries would mask
 * one-shot errors the UI surfaces inline.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        refetchOnWindowFocus: false,
        retry: false,
      },
    },
  });
}

export const queryClient = createQueryClient();
