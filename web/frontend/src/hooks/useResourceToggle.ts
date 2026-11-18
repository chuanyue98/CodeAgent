import { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import request from '../utils/request';
import { useProject, type GroupDefinition } from '../context/ProjectContext';
import { useIsMounted } from './useAsyncGuards';

interface ToggleResult {
  toggleError: string | null;
  dismissToggleError: () => void;
  toggleResource: (
    resourceType: keyof GroupDefinition,
    resourceId: string,
    e?: React.MouseEvent | React.KeyboardEvent
  ) => Promise<void>;
  /**
   * Activates or deactivates many resources in one request instead of one
   * round-trip per item -- toggleResource already sends the *entire* updated
   * list on every call, so batching is just computing that list once for N
   * ids rather than doing it N times.
   */
  toggleResources: (
    resourceType: keyof GroupDefinition,
    resourceIds: string[],
    activate: boolean
  ) => Promise<void>;
}

const EMPTY_GROUP: GroupDefinition = {
  skills: [],
  prompts: [],
  hooks: [],
  plugins: [],
};

/**
 * Shared hook for toggling a resource (skill/plugin/hook/prompt)
 * in the current group. Serializes concurrent mutations and encodes group names.
 */
function useResourceToggle(): ToggleResult {
  const { currentGroup, groups, refreshConfig } = useProject();
  const [toggleError, setToggleError] = useState<string | null>(null);
  const isMounted = useIsMounted();
  const groupsRef = useRef(groups);
  const queueRef = useRef<Promise<void>>(Promise.resolve());

  useEffect(() => {
    groupsRef.current = groups;
  }, [groups]);

  const enqueueMutation = useCallback(
    (
      groupName: string,
      computeNext: (currentGroupDef: GroupDefinition) => GroupDefinition,
      fallbackError: string,
    ): Promise<void> => {
      const run = async () => {
        try {
          if (isMounted()) setToggleError(null);
          const currentGroupDef = groupsRef.current[groupName] || EMPTY_GROUP;
          const nextGroupDef = computeNext(currentGroupDef);
          groupsRef.current = {
            ...groupsRef.current,
            [groupName]: nextGroupDef,
          };

          await request(`/api/groups/${encodeURIComponent(groupName)}`, {
            method: 'POST',
            body: JSON.stringify(nextGroupDef),
          });

          await refreshConfig();
        } catch (err) {
          if (isMounted()) {
            const msg = err instanceof Error ? err.message : fallbackError;
            setToggleError(msg);
          }
        }
      };

      const nextPromise = queueRef.current.then(run, run);
      queueRef.current = nextPromise;
      return nextPromise;
    },
    [isMounted, refreshConfig],
  );

  const toggleResource = useCallback(
    (
      resourceType: keyof GroupDefinition,
      resourceId: string,
      e?: React.MouseEvent | React.KeyboardEvent,
    ) => {
      e?.stopPropagation();
      if (!currentGroup) return Promise.resolve();

      return enqueueMutation(
        currentGroup,
        currentGroupDef => {
          const currentList = [...(currentGroupDef[resourceType] as string[])];
          const index = currentList.indexOf(resourceId);
          if (index > -1) {
            currentList.splice(index, 1);
          } else {
            currentList.push(resourceId);
          }
          return { ...currentGroupDef, [resourceType]: currentList };
        },
        'Failed to toggle resource',
      );
    },
    [currentGroup, enqueueMutation],
  );

  const toggleResources = useCallback(
    (
      resourceType: keyof GroupDefinition,
      resourceIds: string[],
      activate: boolean,
    ) => {
      if (!currentGroup || resourceIds.length === 0) return Promise.resolve();

      return enqueueMutation(
        currentGroup,
        currentGroupDef => {
          const currentList = currentGroupDef[resourceType] as string[];
          const nextList = activate
            ? Array.from(new Set([...currentList, ...resourceIds]))
            : currentList.filter(id => !resourceIds.includes(id));
          return { ...currentGroupDef, [resourceType]: nextList };
        },
        'Failed to update resources',
      );
    },
    [currentGroup, enqueueMutation],
  );

  const dismissToggleError = useCallback(() => setToggleError(null), []);

  return useMemo(
    () => ({ toggleError, dismissToggleError, toggleResource, toggleResources }),
    [toggleError, dismissToggleError, toggleResource, toggleResources],
  );
}

export default useResourceToggle;
