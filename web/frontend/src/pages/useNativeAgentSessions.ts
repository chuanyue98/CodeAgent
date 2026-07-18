import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchNativeAgentSessions } from '../api/agent';
import type { NativeAgentSession, ProviderCapabilities } from '../types/agent';

type NativeSessionState = {
  nativeSessionsByProvider: Record<string, NativeAgentSession[]>;
  nativeLoadingProviders: Set<string>;
  nativeSessionErrors: Record<string, string>;
  loadNativeSessions: (provider: string, force?: boolean) => Promise<void>;
  removeNativeSession: (provider: string, sessionId: string) => void;
};

/** Owns provider-native history loading, caching, and retry state. */
export default function useNativeAgentSessions(
  providers: ProviderCapabilities[],
  selectedProvider: string,
): NativeSessionState {
  const [nativeSessionsByProvider, setNativeSessionsByProvider] = useState<Record<string, NativeAgentSession[]>>({});
  const [nativeLoadingProviders, setNativeLoadingProviders] = useState<Set<string>>(new Set());
  const [nativeSessionErrors, setNativeSessionErrors] = useState<Record<string, string>>({});
  const cacheRef = useRef<Map<string, NativeAgentSession[]>>(new Map());
  const requestsRef = useRef<Map<string, Promise<NativeAgentSession[]>>>(new Map());
  const requestVersionRef = useRef<Map<string, number>>(new Map());

  const loadNativeSessions = useCallback(async (provider: string, force = false) => {
    if (!provider) return;
    let version = requestVersionRef.current.get(provider) || 0;
    if (force) {
      version += 1;
      requestVersionRef.current.set(provider, version);
      cacheRef.current.delete(provider);
      requestsRef.current.delete(provider);
    }
    const cached = cacheRef.current.get(provider);
    if (cached) {
      setNativeSessionsByProvider(previous => ({ ...previous, [provider]: cached }));
      return;
    }
    setNativeLoadingProviders(previous => new Set(previous).add(provider));
    setNativeSessionErrors(previous => {
      const next = { ...previous };
      delete next[provider];
      return next;
    });
    let request = requestsRef.current.get(provider);
    if (!request) {
      version += 1;
      requestVersionRef.current.set(provider, version);
      const requestVersion = version;
      request = fetchNativeAgentSessions(provider)
        .then(result => {
          if (requestVersionRef.current.get(provider) === requestVersion) {
            cacheRef.current.set(provider, result);
          }
          return result;
        })
        .finally(() => {
          if (requestsRef.current.get(provider) === request) {
            requestsRef.current.delete(provider);
          }
        });
      requestsRef.current.set(provider, request);
    }
    try {
      const result = await request;
      if (requestVersionRef.current.get(provider) === version) {
        setNativeSessionsByProvider(previous => ({ ...previous, [provider]: result }));
      }
    } catch {
      if (requestVersionRef.current.get(provider) === version) {
        setNativeSessionErrors(previous => ({
          ...previous,
          [provider]: 'Provider history could not be loaded.',
        }));
      }
    } finally {
      if (requestVersionRef.current.get(provider) === version) {
        setNativeLoadingProviders(previous => {
          const next = new Set(previous);
          next.delete(provider);
          return next;
        });
      }
    }
  }, []);

  useEffect(() => {
    if (selectedProvider) void loadNativeSessions(selectedProvider);
  }, [loadNativeSessions, selectedProvider]);

  useEffect(() => {
    providers.filter(provider => provider.available).forEach(provider => {
      void loadNativeSessions(provider.providerId);
    });
  }, [loadNativeSessions, providers]);

  const removeNativeSession = useCallback((provider: string, sessionId: string) => {
    requestVersionRef.current.set(
      provider,
      (requestVersionRef.current.get(provider) || 0) + 1,
    );
    requestsRef.current.delete(provider);
    setNativeSessionsByProvider(previous => {
      const providerSessions = previous[provider] || [];
      const next = providerSessions.filter(
        session => !(session.engine === provider && session.session_id === sessionId),
      );
      cacheRef.current.set(provider, next);
      return { ...previous, [provider]: next };
    });
    setNativeLoadingProviders(previous => {
      const next = new Set(previous);
      next.delete(provider);
      return next;
    });
  }, []);

  return {
    nativeSessionsByProvider,
    nativeLoadingProviders,
    nativeSessionErrors,
    loadNativeSessions,
    removeNativeSession,
  };
}
