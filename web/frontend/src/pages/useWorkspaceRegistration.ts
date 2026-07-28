import { useCallback, useState } from 'react';
import request from '../utils/request';

export interface UseWorkspaceRegistrationArgs {
  refreshConfig: () => Promise<void>;
  setError: (message: string | null) => void;
}

/** Owns the "register an unregistered workspace" flow. */
export default function useWorkspaceRegistration({ refreshConfig, setError }: UseWorkspaceRegistrationArgs) {
  const [registeringWorkspace, setRegisteringWorkspace] = useState<string | null>(null);

  const registerWorkspace = useCallback(async (path: string) => {
    setRegisteringWorkspace(path);
    try {
      await request('/api/projects', {
        method: 'POST',
        body: JSON.stringify({ path, group: 'common' }),
      });
      await refreshConfig();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to register workspace');
    } finally {
      setRegisteringWorkspace(null);
    }
  }, [refreshConfig, setError]);

  return { registeringWorkspace, registerWorkspace };
}
