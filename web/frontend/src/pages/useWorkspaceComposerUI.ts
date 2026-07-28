import { useCallback, useEffect, useState } from 'react';
import type { RefObject } from 'react';
import type { AgentMessage } from '../state/agentSessionReducer';

export interface UseWorkspaceComposerUIArgs {
  messages: AgentMessage[];
  scrollRef: RefObject<HTMLDivElement | null>;
  composerRef: RefObject<HTMLTextAreaElement | null>;
  hasOlderHistoryRef: RefObject<boolean>;
  loadingOlderHistoryRef: RefObject<boolean>;
  loadOlderHistoryRef: RefObject<() => void>;
}

/** Owns scroll/composer DOM refs and the expanded/collapsed workspace toggles. */
export default function useWorkspaceComposerUI({
  messages,
  scrollRef,
  composerRef,
  hasOlderHistoryRef,
  loadingOlderHistoryRef,
  loadOlderHistoryRef,
}: UseWorkspaceComposerUIArgs) {
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);
  const [expandedWorkspaces, setExpandedWorkspaces] = useState<Set<string>>(new Set());
  const [collapsedWorkspaces, setCollapsedWorkspaces] = useState<Set<string>>(new Set());

  const focusComposer = useCallback(() => {
    composerRef.current?.focus();
  }, [composerRef]);

  const setScrollRef = useCallback((element: HTMLDivElement | null) => {
    scrollRef.current = element;
  }, [scrollRef]);

  const setComposerRef = useCallback((element: HTMLTextAreaElement | null) => {
    composerRef.current = element;
  }, [composerRef]);

  const scrollToLatest = useCallback((behavior: ScrollBehavior = 'smooth') => {
    const element = scrollRef.current;
    if (!element) return;
    element.scrollTo({ top: element.scrollHeight, behavior });
    setShowScrollToBottom(false);
  }, [scrollRef]);

  const onScroll = useCallback((event: React.UIEvent<HTMLDivElement>) => {
    const element = event.currentTarget;
    const distanceFromBottom = element.scrollHeight - element.scrollTop - element.clientHeight;
    setShowScrollToBottom(distanceFromBottom > 120);
    if (element.scrollTop < 120 && hasOlderHistoryRef.current && !loadingOlderHistoryRef.current) {
      loadOlderHistoryRef.current();
    }
  }, [hasOlderHistoryRef, loadingOlderHistoryRef, loadOlderHistoryRef, setShowScrollToBottom]);

  useEffect(() => {
    const element = scrollRef.current;
    if (!element) return;
    const distanceFromBottom = element.scrollHeight - element.scrollTop - element.clientHeight;
    if (distanceFromBottom < 120) scrollToLatest();
  }, [scrollRef, scrollToLatest, messages]);

  const onToggleExpandedWorkspace = useCallback((path: string) => {
    setExpandedWorkspaces(previous => {
      const next = new Set(previous);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }, []);

  const onToggleCollapsedWorkspace = useCallback((path: string) => {
    setCollapsedWorkspaces(previous => {
      const next = new Set(previous);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }, []);

  return {
    showScrollToBottom,
    expandedWorkspaces,
    collapsedWorkspaces,
    focusComposer,
    setScrollRef,
    setComposerRef,
    onScroll,
    scrollToLatest,
    onToggleExpandedWorkspace,
    onToggleCollapsedWorkspace,
  };
}
