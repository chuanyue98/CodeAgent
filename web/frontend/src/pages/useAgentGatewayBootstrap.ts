import { useCallback, useEffect, useState } from 'react';
import {
  fetchAgentGatewayStatus,
  fetchAgentProviders,
  fetchAgentSessions,
} from '../api/agent';
import type { AgentGatewayStatus, AgentSession, ProviderCapabilities } from '../types/agent';

export interface UseAgentGatewayBootstrapArgs {
  setError: (message: string | null) => void;
}

/**
 * Owns the gateway status/providers/session-list bootstrap load and is the
 * sole owner of the session list -- other hooks mutate it only through
 * addSession/removeSession so there's a single place that decides shape.
 */
export default function useAgentGatewayBootstrap({ setError }: UseAgentGatewayBootstrapArgs) {
  const [providers, setProviders] = useState<ProviderCapabilities[]>([]);
  const [gatewayStatus, setGatewayStatus] = useState<AgentGatewayStatus>({
    enabled: true,
    legacyFallback: false,
    providers: {},
  });
  const [sessions, setSessions] = useState<AgentSession[]>([]);
  const [selectedProvider, setSelectedProvider] = useState('');
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const status = await fetchAgentGatewayStatus();
      const [providerList, sessionList] = status.enabled
        ? await Promise.all([fetchAgentProviders(), fetchAgentSessions()])
        : [[], []];
      setGatewayStatus(status);
      setProviders(providerList);
      setSessions(sessionList);
      setSelectedProvider(previous =>
        previous || providerList.find(provider => provider.available)?.providerId || '',
      );
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to load Agent Gateway');
    } finally {
      setLoading(false);
    }
  }, [setError]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
  }, [refresh]);

  const addSession = useCallback((session: AgentSession) => {
    setSessions(previous => [session, ...previous.filter(item => item.id !== session.id)]);
  }, []);

  const removeSession = useCallback((id: string) => {
    setSessions(previous => previous.filter(item => item.id !== id));
  }, []);

  return {
    providers,
    gatewayStatus,
    sessions,
    selectedProvider,
    setSelectedProvider,
    loading,
    refresh,
    addSession,
    removeSession,
  };
}
