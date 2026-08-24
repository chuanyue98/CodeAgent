import { useMemo } from 'react';
import { RESOURCE_KINDS, type ResourceKindConfig } from '../components/resources/resourceKinds';
import type { ResourceData } from '../components/resources/types';
import { useT } from '../i18n/context';
import useResourceData from './useResourceData';

export interface LoadedKind {
  config: ResourceKindConfig;
  /** Category -> items, already reshaped by the kind's transform. */
  data: ResourceData | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
  /** Total items across every category of this kind. */
  count: number;
}

export interface AllResourceData {
  kinds: LoadedKind[];
  /** True until every kind has settled, so the page shows one spinner. */
  loading: boolean;
  /** Kinds that failed, for a partial-failure notice. */
  failed: LoadedKind[];
  refetchAll: () => void;
}

/**
 * Loads all four group-scoped resource kinds at once.
 *
 * The kinds are a fixed module constant, so calling `useResourceData` once
 * per kind is unconditional and stable — this cannot be a loop over dynamic
 * data without breaking the rules of hooks, and the explicit calls make that
 * constraint visible rather than hidden behind a clever abstraction.
 *
 * Fetching all four is what makes one search box possible: "was that thing a
 * skill or a hook?" is unanswerable while each kind lives behind its own tab.
 */
export default function useAllResourceData(): AllResourceData {
  const t = useT();

  const [skills, prompts, hooks, plugins] = RESOURCE_KINDS;
  const skillsResult = useResourceData<unknown>(skills.apiEndpoint);
  const promptsResult = useResourceData<unknown>(prompts.apiEndpoint);
  const hooksResult = useResourceData<unknown>(hooks.apiEndpoint);
  const pluginsResult = useResourceData<unknown>(plugins.apiEndpoint);

  const results = [skillsResult, promptsResult, hooksResult, pluginsResult];

  return useMemo(() => {
    const kinds: LoadedKind[] = RESOURCE_KINDS.map((config, index) => {
      const result = results[index];
      const raw = result.data;
      const data = raw
        ? config.transformData
          ? config.transformData(raw, t)
          : (raw as ResourceData)
        : null;
      const count = data
        ? Object.values(data).reduce((sum, items) => sum + items.length, 0)
        : 0;
      return {
        config,
        data,
        loading: result.loading,
        error: result.error,
        refetch: result.refetch,
        count,
      };
    });

    return {
      kinds,
      loading: kinds.some(kind => kind.loading),
      failed: kinds.filter(kind => kind.error !== null),
      refetchAll: () => kinds.forEach(kind => kind.refetch()),
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    skillsResult.data, skillsResult.loading, skillsResult.error, skillsResult.refetch,
    promptsResult.data, promptsResult.loading, promptsResult.error, promptsResult.refetch,
    hooksResult.data, hooksResult.loading, hooksResult.error, hooksResult.refetch,
    pluginsResult.data, pluginsResult.loading, pluginsResult.error, pluginsResult.refetch,
    t,
  ]);
}
