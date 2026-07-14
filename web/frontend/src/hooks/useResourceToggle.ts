import { useState, useCallback } from 'react';
import request from '../utils/request';
import { useProject, type GroupDefinition } from '../context/ProjectContext';

interface ToggleResult {
  toggleError: string | null;
  toggleResource: (
    resourceType: keyof GroupDefinition,
    resourceId: string,
    e?: React.MouseEvent | React.KeyboardEvent
  ) => Promise<void>;
}

/**
 * Shared hook for toggling a resource (skill/plugin/hook/prompt)
 * in the current group. Handles the POST request and config refresh.
 */
function useResourceToggle(): ToggleResult {
  const { currentGroup, groups, refreshConfig } = useProject();
  const [toggleError, setToggleError] = useState<string | null>(null);

  const toggleResource = useCallback(
    async (
      resourceType: keyof GroupDefinition,
      resourceId: string,
      e?: React.MouseEvent | React.KeyboardEvent
    ) => {
      e?.stopPropagation();
      if (!currentGroup) return;

      try {
        setToggleError(null);
        const currentGroupDef = groups[currentGroup] || {
          skills: [],
          prompts: [],
          hooks: [],
          plugins: [],
        };
        const currentList = [...(currentGroupDef[resourceType] as string[])];
        const index = currentList.indexOf(resourceId);

        if (index > -1) {
          currentList.splice(index, 1);
        } else {
          currentList.push(resourceId);
        }

        await request(`/api/groups/${currentGroup}`, {
          method: 'POST',
          body: JSON.stringify({ ...currentGroupDef, [resourceType]: currentList }),
        });

        await refreshConfig();
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Failed to toggle resource';
        setToggleError(msg);
      }
    },
    [currentGroup, groups, refreshConfig]
  );

  return { toggleError, toggleResource };
}

export default useResourceToggle;
