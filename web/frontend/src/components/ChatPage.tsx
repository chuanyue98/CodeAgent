import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Send, MessageSquare, Plus, AlertCircle, Loader2, RotateCcw, Square, FolderGit2, ArrowDown } from 'lucide-react';
import { Link } from 'react-router';
import { useProject } from '../context/ProjectContext';
import request from '../utils/request';
import MarkdownMessage from './MarkdownMessage';
import SessionCapabilities from './SessionCapabilities';
import {
  cancelChatTurn,
  fetchChatEngines,
  fetchResumableSessions,
  startChatTurn,
  useChatTurnStream,
  type ChatEngine,
  type SessionSummary,
} from '../api/chat';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'error';
  text: string;
}

interface SessionDetailMessage {
  role: string;
  content: string;
}

/** Extracts human-readable text from one raw engine JSON(L) event.
 *  Each engine's event carries the *full* text for that step (not a
 *  delta), matching what was observed live — see
 *  docs/chatpage-cli-spike-results.md. Returns null for events that
 *  don't carry displayable assistant text (status/system/usage events).
 */
function extractAssistantText(engine: string, event: Record<string, unknown>): string | null {
  if (engine === 'claude') {
    if (event.type === 'assistant' && event.message && typeof event.message === 'object') {
      const content = (event.message as { content?: unknown }).content;
      if (Array.isArray(content)) {
        const text = content
          .filter((b): b is { type: string; text: string } => !!b && typeof b === 'object' && (b as { type?: string }).type === 'text')
          .map(b => b.text)
          .join('');
        if (text) return text;
      }
    }
    if (event.type === 'result' && typeof event.result === 'string') {
      return event.result;
    }
    return null;
  }

  if (engine === 'codex') {
    if (event.type === 'item.completed' && event.item && typeof event.item === 'object') {
      const item = event.item as { type?: string; text?: string };
      if (item.type === 'agent_message' && typeof item.text === 'string') {
        return item.text;
      }
    }
    return null;
  }

  if (engine === 'opencode') {
    if (event.type === 'text' && event.part && typeof event.part === 'object') {
      const text = (event.part as { text?: string }).text;
      if (typeof text === 'string') return text;
    }
    return null;
  }

  // gemini: -o json shape unconfirmed (auth blocked during the spike — see
  // docs/chatpage-cli-spike-results.md). Best-effort fallback field probing.
  for (const key of ['text', 'response', 'result', 'message']) {
    const value = event[key];
    if (typeof value === 'string' && value.trim()) return value;
  }
  return null;
}

export default function ChatPage() {
  const { currentGroup, projects, setCurrentGroup } = useProject();
  const [engines, setEngines] = useState<ChatEngine[]>([]);
  const [selectedEngine, setSelectedEngine] = useState<string>('');
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [activeProjectPath, setActiveProjectPath] = useState<string | null>(null);
  const [unregisteredSessionPath, setUnregisteredSessionPath] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [turnId, setTurnId] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [canceling, setCanceling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  // Pauses auto-scroll while the user is reading history, so streaming
  // output no longer yanks them back to the bottom on every token.
  const [isUserScrolledUp, setIsUserScrolledUp] = useState(false);

  const { events, done, error: streamError } = useChatTurnStream(turnId);

  // Guards setState calls in async fetches below from firing after the
  // component has unmounted (e.g. a fast workspace/page switch while a
  // request is still in flight).
  const mountedRef = useRef(true);
  useEffect(() => {
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // Each event carries the *full* text for its step (not a delta — see
  // extractAssistantText), so the latest text-bearing event is always the
  // complete in-progress answer. Computing this during render (rather than
  // via a useEffect + ref) means it can never observe a stale events array
  // from a previous turn.
  const pendingText = useMemo(() => {
    for (let i = events.length - 1; i >= 0; i--) {
      const text = extractAssistantText(selectedEngine, events[i]);
      if (text) return text;
    }
    return '';
  }, [events, selectedEngine]);

  const currentEngine = engines.find(e => e.id === selectedEngine);
  const visibleSessions = sessions;

  useEffect(() => {
    if (activeProjectPath && projects.some(project => project.path === activeProjectPath)) return;
    if (projects.length === 1 && !activeSessionId) {
      const [project] = projects;
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setActiveProjectPath(project.path);
      setCurrentGroup(project.group);
    } else if (!activeSessionId) {
      setActiveProjectPath(null);
    }
  }, [activeProjectPath, activeSessionId, projects, setCurrentGroup]);

  useEffect(() => {
    fetchChatEngines()
      .then(list => {
        if (!mountedRef.current) return;
        setEngines(list);
        if (list.length > 0) setSelectedEngine(prev => prev || list[0].id);
      })
      .catch(() => {
        if (!mountedRef.current) return;
        setError('Failed to load engines');
      });
  }, []);

  const loadSessions = useCallback((engine: string) => {
    setSessionsLoading(true);
    fetchResumableSessions(engine, 30)
      .then(list => {
        if (!mountedRef.current) return;
        setSessions(list);
        setSessionsLoading(false);
      })
      .catch(() => {
        if (!mountedRef.current) return;
        setSessionsLoading(false);
      });
  }, []);

  useEffect(() => {
    if (!selectedEngine) return;
    const engine = engines.find(e => e.id === selectedEngine);
    if (engine?.supportsResume) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      loadSessions(selectedEngine);
    } else {
      setSessions([]);
    }
  }, [selectedEngine, engines, loadSessions]);

  const startNewSession = () => {
    if (sending) return;
    setActiveSessionId(null);
    setUnregisteredSessionPath(null);
    setMessages([]);
    setError(null);
  };

  const continueSession = async (session: SessionSummary) => {
    if (sending) return;
    const project = projects.find(candidate => candidate.path === session.project_path);
    setActiveSessionId(session.session_id);
    if (project) {
      setActiveProjectPath(session.project_path);
      setUnregisteredSessionPath(null);
      setCurrentGroup(project.group);
    } else {
      setActiveProjectPath(null);
      setUnregisteredSessionPath(session.project_path);
    }
    setError(null);
    try {
      const detail = await request<{ messages: SessionDetailMessage[] }>(
        `/api/history/${session.engine}/${session.session_id}?project=${encodeURIComponent(session.project_path)}`,
      );
      const priorMessages: SessionDetailMessage[] = detail?.messages || [];
      setMessages(
        priorMessages
          .filter(m => m.role === 'user' || m.role === 'assistant')
          .map(m => ({ id: crypto.randomUUID(), role: m.role as 'user' | 'assistant', text: m.content || '' })),
      );
    } catch {
      setError('Failed to load session history');
      setActiveSessionId(null);
      setActiveProjectPath(null);
      setUnregisteredSessionPath(null);
      setMessages([]);
    }
  };

  useEffect(() => {
    if (!done) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMessages(prev => {
      if (done.status !== 'completed') {
        return [...prev, { id: crypto.randomUUID(), role: 'error' as const, text: `Turn ${done.status}` }];
      }
      if (pendingText) {
        return [...prev, { id: crypto.randomUUID(), role: 'assistant' as const, text: pendingText }];
      }
      return prev;
    });
    if (done.session_id) {
      setActiveSessionId(done.session_id);
    }
    setTurnId(null);
    setSending(false);
    setCanceling(false);
  }, [done, pendingText]);

  useEffect(() => {
    if (streamError) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setError(streamError);
      setSending(false);
      setCanceling(false);
      setTurnId(null);
    }
  }, [streamError]);

  useEffect(() => {
    if (isUserScrolledUp) return;
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, pendingText, isUserScrolledUp]);

  const handleScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    setIsUserScrolledUp(distanceFromBottom > 120);
  };

  const scrollToBottom = () => {
    setIsUserScrolledUp(false);
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  };

  const send = async () => {
    const text = input.trim();
    if (!text || sending || !selectedEngine) return;
    if (!activeProjectPath) {
      setError('Select a registered workspace before sending a message');
      return;
    }

    setMessages(prev => [...prev, { id: crypto.randomUUID(), role: 'user' as const, text }]);
    setInput('');
    requestAnimationFrame(() => {
      if (composerRef.current) composerRef.current.style.height = 'auto';
    });
    setSending(true);
    setError(null);

    try {
      const status = await startChatTurn({
        engine: selectedEngine,
        message: text,
        session_id: activeSessionId,
        group: currentGroup || 'common',
        project_path: activeProjectPath,
      });
      setTurnId(status.task_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to start turn');
      setSending(false);
    }
  };

  const cancel = async () => {
    if (!turnId || canceling) return;
    setCanceling(true);
    setError(null);
    try {
      await cancelChatTurn(turnId);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to cancel turn');
      setCanceling(false);
    }
  };

  const selectWorkspace = (path: string) => {
    if (sending) return;
    const project = projects.find(candidate => candidate.path === path);
    setActiveProjectPath(path || null);
    setActiveSessionId(null);
    setUnregisteredSessionPath(null);
    setMessages([]);
    setError(null);
    if (project) setCurrentGroup(project.group);
  };

  const selectEngine = (engine: string) => {
    if (sending || engine === selectedEngine) return;
    setSelectedEngine(engine);
    startNewSession();
  };

  const resizeComposer = (element: HTMLTextAreaElement) => {
    element.style.height = 'auto';
    element.style.height = `${Math.min(element.scrollHeight, 160)}px`;
  };

  return (
    <div className="flex min-h-full flex-col gap-3 lg:h-full lg:flex-row">
      <aside className="glass-card flex w-full shrink-0 flex-col p-3 lg:w-60">
        <div className="mb-3 flex items-center justify-between gap-2 border-b border-slate-100 pb-3">
          <span className="flex items-center gap-2 text-sm font-semibold text-slate-700">
            <MessageSquare className="h-4 w-4" /> Conversations
          </span>
          <button
            onClick={startNewSession}
            disabled={sending}
            className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs font-semibold text-primary hover:bg-primary/10 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Plus className="h-3.5 w-3.5" /> New
          </button>
        </div>

        <div className="min-h-0 flex-1">
          <p className="mb-1.5 text-xs font-medium text-slate-400">
            {currentEngine?.supportsResume ? 'Recent' : 'Resume unavailable'}
          </p>
          {!currentEngine?.supportsResume && (
            <p className="text-[10px] text-slate-400 italic" title="Gemini's individual-tier Code Assist client is sunset; session resume was never confirmed to carry context forward.">
              Not supported for this engine yet
            </p>
          )}
          {currentEngine?.supportsResume && (
            <div className="custom-scrollbar space-y-1 overflow-y-auto">
              {sessionsLoading && <p className="text-xs text-slate-400">Loading...</p>}
              {!sessionsLoading && visibleSessions.length === 0 && (
                <p className="text-xs text-slate-400 italic">No prior sessions</p>
              )}
              {visibleSessions.map(session => (
                <button
                  key={session.session_id}
                  onClick={() => continueSession(session)}
                  disabled={sending}
                  className={`w-full rounded-md px-2 py-1.5 text-left text-xs transition-colors ${
                    activeSessionId === session.session_id
                      ? 'bg-primary/10 text-primary font-medium'
                      : 'text-slate-500 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40'
                  }`}
                  title={session.title}
                >
                  <span className="block truncate">{session.title || session.session_id}</span>
                  <span className="mt-0.5 block truncate text-[10px] font-normal opacity-70">{session.project_path}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </aside>

      <div className="glass-card flex min-w-0 flex-1 flex-col p-3 sm:p-4">
        <div className="mb-3 flex flex-wrap items-end gap-2 border-b border-slate-100 pb-3">
          <label className="min-w-52 flex-1 text-[11px] font-medium text-slate-500">
            Workspace
            <span className="relative mt-1 flex items-center">
              <FolderGit2 className="pointer-events-none absolute left-2.5 h-3.5 w-3.5 text-slate-400" />
              <select
                aria-label="Workspace"
                value={activeProjectPath ?? ''}
                onChange={event => selectWorkspace(event.target.value)}
                disabled={sending || projects.length === 0}
                className="w-full rounded-lg border border-slate-200 bg-white py-2 pl-8 pr-8 text-xs text-slate-700 outline-none focus:border-primary disabled:opacity-50"
              >
                <option value="">Select a registered workspace</option>
                {projects.map(project => (
                  <option key={project.path} value={project.path}>{project.path}</option>
                ))}
              </select>
            </span>
          </label>

          <label className="min-w-40 text-[11px] font-medium text-slate-500">
            Provider
            <select
              aria-label="Provider"
              value={selectedEngine}
              onChange={event => selectEngine(event.target.value)}
              disabled={sending || engines.length === 0}
              className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-700 outline-none focus:border-primary disabled:opacity-50"
            >
              {engines.map(engine => <option key={engine.id} value={engine.id}>{engine.name}</option>)}
            </select>
          </label>

          <span className="rounded-md border border-amber-200 bg-amber-50 px-2 py-1.5 text-[10px] font-semibold text-amber-800">
            Legacy restricted
          </span>
          {activeSessionId && (
            <span className="flex items-center gap-1 text-[10px] font-mono text-slate-400">
              <RotateCcw className="w-3 h-3" /> {activeSessionId.slice(0, 12)}...
            </span>
          )}
        </div>

        {projects.length === 0 && !unregisteredSessionPath && (
          <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
            Register a workspace before starting a conversation.{' '}
            <Link className="font-semibold underline" to="/settings/workspace">Open Workspace settings</Link>
          </div>
        )}

        {unregisteredSessionPath && (
          <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
            <p className="font-semibold">Viewing an existing session in read-only mode</p>
            <p className="mt-0.5 break-all text-amber-800">{unregisteredSessionPath}</p>
            <p className="mt-1">
              Register this directory as a Workspace before continuing the conversation.{' '}
              <Link className="font-semibold underline" to="/settings/workspace">Open Workspace settings</Link>
            </p>
          </div>
        )}

        {error && (
          <div className="mb-3 flex items-center gap-2 px-3 py-2 bg-red-50/60 border border-red-100 rounded-lg text-xs text-red-600">
            <AlertCircle className="w-3.5 h-3.5 shrink-0" /> {error}
          </div>
        )}

        {activeProjectPath && (
          <SessionCapabilities
            engine={selectedEngine}
            group={currentGroup || 'common'}
            projectPath={activeProjectPath}
          />
        )}

        <div className="relative flex min-h-0 flex-1">
          <div ref={scrollRef} onScroll={handleScroll} className="h-full overflow-y-auto space-y-3 pr-1">
          {messages.length === 0 && !sending && (
            <p className="text-sm text-slate-400 text-center py-8">
              {activeProjectPath
                ? `Start a conversation with ${currentEngine?.name || 'an engine'}.`
                : 'Select a registered workspace to start.'}
            </p>
          )}
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`max-w-[85%] rounded-xl px-4 py-2.5 text-sm whitespace-pre-wrap break-words prose prose-slate ${
                msg.role === 'user'
                  ? 'ml-auto bg-primary/10 text-slate-800'
                  : msg.role === 'error'
                    ? 'bg-red-50 text-red-600 border border-red-100'
                    : 'bg-slate-50 text-slate-700 border border-slate-100'
              }`}
            >
              {msg.role === 'assistant' ? (
                <MarkdownMessage text={msg.text || '(empty response)'} />
              ) : (
                msg.text
              )}
            </div>
          ))}
          {sending && (
            <div className={`max-w-[85%] rounded-xl px-4 py-2.5 text-sm whitespace-pre-wrap break-words prose prose-slate bg-slate-50 text-slate-700 border border-slate-100`}>
              {pendingText ? (
                <MarkdownMessage text={pendingText} />
              ) : (
                <span className="flex items-center gap-2 text-slate-400">
                  <Loader2 className="w-3.5 h-3.5 animate-spin" /> Thinking...
                </span>
              )}
            </div>
          )}
          </div>
          {isUserScrolledUp && (
            <button
              type="button"
              onClick={scrollToBottom}
              aria-label="Jump to latest message"
              className="absolute bottom-3 left-1/2 -translate-x-1/2 flex items-center gap-1 rounded-full bg-slate-800 px-3 py-1.5 text-xs font-medium text-white shadow-lg hover:bg-slate-700"
            >
              <ArrowDown className="h-3.5 w-3.5" /> Jump to latest
            </button>
          )}
        </div>

        <div className="mt-3 flex items-end gap-2">
          <textarea
            ref={composerRef}
            value={input}
            onChange={e => {
              setInput(e.target.value);
              resizeComposer(e.target);
            }}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
            placeholder="Message the engine... (Enter to send, Shift+Enter for newline)"
            rows={1}
            disabled={sending}
            className="max-h-40 min-h-10 flex-1 resize-none overflow-y-auto rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:border-primary focus:outline-none disabled:opacity-50"
          />
          {sending ? (
            <button
              onClick={() => void cancel()}
              disabled={canceling || !turnId}
              aria-label="Cancel turn"
              title="Cancel turn"
              className="rounded-lg border border-red-200 bg-red-50 p-2.5 text-red-600 transition-colors hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {canceling ? <Loader2 className="h-4 w-4 animate-spin" /> : <Square className="h-4 w-4 fill-current" />}
            </button>
          ) : (
            <button
              onClick={() => void send()}
              disabled={!input.trim() || !activeProjectPath}
              aria-label="Send message"
              className="rounded-lg bg-primary p-2.5 text-white transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Send className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
