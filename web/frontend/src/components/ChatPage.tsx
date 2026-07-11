import { useState, useEffect, useCallback, useRef } from 'react';
import { Send, MessageSquare, Plus, AlertCircle, Loader2, RotateCcw } from 'lucide-react';
import { useProject } from '../context/ProjectContext';
import {
  fetchChatEngines,
  fetchResumableSessions,
  startChatTurn,
  useChatTurnStream,
  type ChatEngine,
  type SessionSummary,
} from '../api/chat';

interface ChatMessage {
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
  const { currentGroup } = useProject();
  const [engines, setEngines] = useState<ChatEngine[]>([]);
  const [selectedEngine, setSelectedEngine] = useState<string>('');
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [turnId, setTurnId] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pendingTextRef = useRef('');
  const [pendingText, setPendingText] = useState('');
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const { events, done, error: streamError } = useChatTurnStream(turnId);

  const currentEngine = engines.find(e => e.id === selectedEngine);

  useEffect(() => {
    fetchChatEngines()
      .then(list => {
        setEngines(list);
        if (list.length > 0) setSelectedEngine(prev => prev || list[0].id);
      })
      .catch(() => setError('Failed to load engines'));
  }, []);

  const loadSessions = useCallback((engine: string) => {
    setSessionsLoading(true);
    fetchResumableSessions(engine, 30)
      .then(list => {
        setSessions(list);
        setSessionsLoading(false);
      })
      .catch(() => setSessionsLoading(false));
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
    setActiveSessionId(null);
    setMessages([]);
    setError(null);
  };

  const continueSession = async (session: SessionSummary) => {
    setActiveSessionId(session.session_id);
    setError(null);
    try {
      const res = await fetch(
        `/api/history/${session.engine}/${session.session_id}?project=${encodeURIComponent(session.project_path)}`,
      );
      if (res.ok) {
        const detail = await res.json();
        const priorMessages: SessionDetailMessage[] = detail.messages || [];
        setMessages(
          priorMessages
            .filter(m => m.role === 'user' || m.role === 'assistant')
            .map(m => ({ role: m.role as 'user' | 'assistant', text: m.content || '' })),
        );
      } else {
        setMessages([]);
      }
    } catch {
      setMessages([]);
    }
  };

  // Track the latest full text per in-flight turn (each event carries the
  // full step text, not a delta — see extractAssistantText).
  useEffect(() => {
    if (!turnId || events.length === 0) return;
    for (let i = events.length - 1; i >= 0; i--) {
      const text = extractAssistantText(selectedEngine, events[i]);
      if (text) {
        pendingTextRef.current = text;
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setPendingText(text);
        break;
      }
    }
  }, [events, turnId, selectedEngine]);

  useEffect(() => {
    if (!done) return;
    const finalText = pendingTextRef.current;
    setMessages(prev => {
      if (done.status !== 'completed') {
        return [...prev, { role: 'error', text: `Turn ${done.status}` }];
      }
      if (finalText) {
        return [...prev, { role: 'assistant', text: finalText }];
      }
      return prev;
    });
    if (done.session_id) {
      setActiveSessionId(done.session_id);
    }
    pendingTextRef.current = '';
    setPendingText('');
    setTurnId(null);
    setSending(false);
  }, [done]);

  useEffect(() => {
    if (streamError) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setError(streamError);
      setSending(false);
      setTurnId(null);
    }
  }, [streamError]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, pendingText]);

  const send = async () => {
    const text = input.trim();
    if (!text || sending || !selectedEngine) return;

    setMessages(prev => [...prev, { role: 'user', text }]);
    setInput('');
    setSending(true);
    setError(null);

    try {
      const status = await startChatTurn({
        engine: selectedEngine,
        message: text,
        session_id: activeSessionId,
        group: currentGroup || 'common',
      });
      setTurnId(status.task_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to start turn');
      setSending(false);
    }
  };

  return (
    <div className="flex gap-4 h-full">
      <div className="w-64 shrink-0 glass-card p-4 space-y-4 flex flex-col">
        <div>
          <label className="text-xs text-slate-400 font-medium block mb-1">Engine</label>
          <div className="space-y-1">
            {engines.map(engine => (
              <button
                key={engine.id}
                onClick={() => {
                  setSelectedEngine(engine.id);
                  startNewSession();
                }}
                className={`w-full text-left px-2 py-1.5 rounded-md text-xs transition-colors ${
                  selectedEngine === engine.id
                    ? 'bg-slate-100 text-slate-800 font-medium'
                    : 'text-slate-500 hover:bg-slate-50'
                }`}
              >
                {engine.name}
              </button>
            ))}
          </div>
        </div>

        <button
          onClick={startNewSession}
          className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-xs font-medium transition-colors ${
            activeSessionId === null ? 'bg-primary/10 text-primary' : 'text-slate-500 hover:bg-slate-50'
          }`}
        >
          <Plus className="w-3.5 h-3.5" /> New session
        </button>

        <div className="flex-1 min-h-0 flex flex-col">
          <label className="text-xs text-slate-400 font-medium block mb-1">
            {currentEngine?.supportsResume ? 'Continue session' : 'Resume unavailable'}
          </label>
          {!currentEngine?.supportsResume && (
            <p className="text-[10px] text-slate-400 italic" title="Gemini's individual-tier Code Assist client is sunset; session resume was never confirmed to carry context forward.">
              Not supported for this engine yet
            </p>
          )}
          {currentEngine?.supportsResume && (
            <div className="space-y-1 overflow-y-auto">
              {sessionsLoading && <p className="text-xs text-slate-400">Loading...</p>}
              {!sessionsLoading && sessions.length === 0 && (
                <p className="text-xs text-slate-400 italic">No prior sessions</p>
              )}
              {sessions.map(session => (
                <button
                  key={session.session_id}
                  onClick={() => continueSession(session)}
                  className={`w-full text-left px-2 py-1.5 rounded-md text-xs transition-colors truncate ${
                    activeSessionId === session.session_id
                      ? 'bg-primary/10 text-primary font-medium'
                      : 'text-slate-500 hover:bg-slate-50'
                  }`}
                  title={session.title}
                >
                  {session.title || session.session_id}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 min-w-0 glass-card p-5 flex flex-col">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">
            <MessageSquare className="w-4 h-4" /> Chat
          </div>
          {activeSessionId && (
            <span className="flex items-center gap-1 text-[10px] text-slate-400 font-mono">
              <RotateCcw className="w-3 h-3" /> {activeSessionId.slice(0, 12)}...
            </span>
          )}
        </div>

        {error && (
          <div className="mb-3 flex items-center gap-2 px-3 py-2 bg-red-50/60 border border-red-100 rounded-lg text-xs text-red-600">
            <AlertCircle className="w-3.5 h-3.5 shrink-0" /> {error}
          </div>
        )}

        <div ref={scrollRef} className="flex-1 overflow-y-auto space-y-3 pr-1">
          {messages.length === 0 && !sending && (
            <p className="text-sm text-slate-400 text-center py-8">
              Start a conversation with {currentEngine?.name || 'an engine'}.
            </p>
          )}
          {messages.map((msg, i) => (
            <div
              key={i}
              className={`max-w-[85%] rounded-xl px-3 py-2 text-sm whitespace-pre-wrap break-words ${
                msg.role === 'user'
                  ? 'ml-auto bg-primary/10 text-slate-800'
                  : msg.role === 'error'
                    ? 'bg-red-50 text-red-600 border border-red-100'
                    : 'bg-slate-50 text-slate-700 border border-slate-100'
              }`}
            >
              {msg.text || (msg.role === 'assistant' ? '(empty response)' : '')}
            </div>
          ))}
          {sending && (
            <div className="bg-slate-50 text-slate-700 border border-slate-100 rounded-xl px-3 py-2 text-sm max-w-[85%] whitespace-pre-wrap break-words">
              {pendingText || (
                <span className="flex items-center gap-2 text-slate-400">
                  <Loader2 className="w-3.5 h-3.5 animate-spin" /> Thinking...
                </span>
              )}
            </div>
          )}
        </div>

        <div className="mt-3 flex items-end gap-2">
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
            placeholder="Message the engine..."
            rows={2}
            disabled={sending}
            className="flex-1 px-3 py-2 text-sm border border-slate-200 rounded-lg bg-white focus:outline-none focus:border-primary resize-none disabled:opacity-50"
          />
          <button
            onClick={() => void send()}
            disabled={sending || !input.trim()}
            className="p-2.5 bg-primary text-white rounded-lg disabled:opacity-40 disabled:cursor-not-allowed hover:scale-105 active:scale-95 transition-all"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
