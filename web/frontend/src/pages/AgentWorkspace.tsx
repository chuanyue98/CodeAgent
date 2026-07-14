import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from 'react';
import {
  Activity,
  AlertCircle,
  Bot,
  ChevronRight,
  FolderGit2,
  Loader2,
  MessageSquare,
  Plus,
  Send,
  ShieldCheck,
  Square,
  Wifi,
  WifiOff,
  X,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { Link } from 'react-router-dom';
import {
  agentEventsUrl,
  createAgentSession,
  fetchAgentProviders,
  fetchAgentSessions,
  resumeAgentSession,
  sendAgentCommand,
} from '../api/agent';
import ChatPage from '../components/ChatPage';
import { useProject } from '../context/ProjectContext';
import {
  agentSessionReducer,
  initialAgentSessionState,
} from '../state/agentSessionReducer';
import type {
  AgentAck,
  AgentError,
  AgentEvent,
  AgentSession,
  ApprovalDecision,
  PermissionMode,
  ProviderCapabilities,
} from '../types/agent';

function requestId(): string {
  return crypto.randomUUID();
}

export default function AgentWorkspace() {
  const { projects, setCurrentGroup } = useProject();
  const [providers, setProviders] = useState<ProviderCapabilities[]>([]);
  const [sessions, setSessions] = useState<AgentSession[]>([]);
  const [selectedProvider, setSelectedProvider] = useState('');
  const [workspace, setWorkspace] = useState('');
  const [permissionMode, setPermissionMode] = useState<PermissionMode>('workspace-write');
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showActivity, setShowActivity] = useState(false);
  const [legacyMode, setLegacyMode] = useState(false);
  const [state, dispatch] = useReducer(agentSessionReducer, initialAgentSessionState);
  const stateRef = useRef(state);
  const socketRef = useRef<WebSocket | null>(null);
  const intentionalClose = useRef(false);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [providerList, sessionList] = await Promise.all([
        fetchAgentProviders(),
        fetchAgentSessions(),
      ]);
      setProviders(providerList);
      setSessions(sessionList);
      setSelectedProvider(previous => previous || providerList.find(provider => provider.available)?.providerId || '');
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to load Agent Gateway');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!workspace && projects.length === 1) {
      const [project] = projects;
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setWorkspace(project.path);
      setCurrentGroup(project.group);
    }
  }, [projects, setCurrentGroup, workspace]);

  useEffect(() => () => {
    intentionalClose.current = true;
    socketRef.current?.close();
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [state.messages]);

  const connect = useCallback((session: AgentSession, afterSequence = 0, reset = true) => {
    intentionalClose.current = true;
    if (socketRef.current) {
      socketRef.current.onclose = null;
      socketRef.current.close();
    }
    intentionalClose.current = false;
    if (reset) dispatch({ type: 'reset', session });
    setConnecting(true);
    setConnected(false);
    setError(null);

    return new Promise<WebSocket>((resolve, reject) => {
      const socket = new WebSocket(agentEventsUrl(session.id, afterSequence));
      socketRef.current = socket;
      socket.onopen = () => {
        setConnecting(false);
        setConnected(true);
        resolve(socket);
      };
      socket.onmessage = event => {
        try {
          const message = JSON.parse(event.data) as AgentEvent | AgentAck | AgentError;
          if (message.type === 'ack') return;
          if (message.type === 'error' && !('sequence' in message)) {
            setError(message.message);
            return;
          }
          dispatch({ type: 'event', event: message as AgentEvent });
        } catch {
          setError('Received an invalid Gateway event');
        }
      };
      socket.onerror = () => {
        setError('Agent connection failed');
      };
      socket.onclose = () => {
        setConnecting(false);
        setConnected(false);
        if (!intentionalClose.current) {
          setError('Agent connection closed. Reconnect to continue from the last event.');
        }
      };
      const timer = window.setTimeout(() => {
        if (socket.readyState !== WebSocket.OPEN) {
          socket.close();
          reject(new Error('Agent connection timed out'));
        }
      }, 10_000);
      socket.addEventListener('open', () => window.clearTimeout(timer), { once: true });
    });
  }, []);

  const selectSession = async (session: AgentSession) => {
    if (state.activeTurnId) return;
    try {
      const resumed = await resumeAgentSession(session.id);
      setWorkspace(resumed.projectId);
      setSelectedProvider(resumed.provider);
      setPermissionMode(resumed.permissionMode);
      await connect(resumed, 0, true);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to resume session');
    }
  };

  const newSession = () => {
    intentionalClose.current = true;
    socketRef.current?.close();
    socketRef.current = null;
    setConnected(false);
    setError(null);
    dispatch({ type: 'reset' });
  };

  const send = async () => {
    const text = input.trim();
    if (!text || state.activeTurnId || connecting) return;
    if (!workspace || !selectedProvider) {
      setError('Select a registered workspace and an available provider');
      return;
    }
    setInput('');
    if (composerRef.current) composerRef.current.style.height = 'auto';
    try {
      let session = state.session;
      let socket = socketRef.current;
      if (!session) {
        session = await createAgentSession({
          provider: selectedProvider,
          projectId: workspace,
          permissionMode,
          title: text.slice(0, 80),
        });
        setSessions(previous => [session as AgentSession, ...previous]);
        socket = await connect(session, 0, true);
      } else if (!socket || socket.readyState !== WebSocket.OPEN) {
        socket = await connect(session, stateRef.current.lastSequence, false);
      }
      sendAgentCommand(socket, {
        type: 'turn.start',
        requestId: requestId(),
        sessionId: session.id,
        input: [{ type: 'text', text }],
      });
    } catch (caught) {
      setInput(text);
      setError(caught instanceof Error ? caught.message : 'Failed to start turn');
    }
  };

  const cancel = () => {
    const socket = socketRef.current;
    if (!socket || !state.session || !state.activeTurnId) return;
    try {
      sendAgentCommand(socket, {
        type: 'turn.cancel',
        requestId: requestId(),
        sessionId: state.session.id,
        turnId: state.activeTurnId,
      });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to cancel turn');
    }
  };

  const respondApproval = (approvalId: string, decision: ApprovalDecision) => {
    const socket = socketRef.current;
    if (!socket || !state.session) return;
    try {
      sendAgentCommand(socket, {
        type: 'approval.respond',
        requestId: requestId(),
        sessionId: state.session.id,
        approvalId,
        decision,
      });
      dispatch({ type: 'approval.resolved', approvalId });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to respond to approval');
    }
  };

  const selectedCapabilities = providers.find(provider => provider.providerId === selectedProvider);
  const availableProviders = providers.filter(provider => provider.available);
  const noGatewayProvider = !loading && availableProviders.length === 0;
  const recentSessions = useMemo(() => sessions.slice(0, 40), [sessions]);

  if (legacyMode) {
    return (
      <div className="space-y-3">
        <div className="flex items-center justify-between rounded-xl border border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-900">
          <span>Legacy chat uses one-shot provider processes and has limited interaction.</span>
          <button className="font-semibold underline" onClick={() => setLegacyMode(false)}>Try Agent Gateway</button>
        </div>
        <ChatPage />
      </div>
    );
  }

  return (
    <div className="flex min-h-full gap-3 lg:h-full">
      <aside className="glass-card flex w-60 shrink-0 flex-col p-3">
        <div className="mb-3 flex items-center justify-between border-b border-slate-100 pb-3">
          <span className="flex items-center gap-2 text-sm font-semibold text-slate-700">
            <MessageSquare className="h-4 w-4" /> Conversations
          </span>
          <button
            onClick={newSession}
            disabled={Boolean(state.activeTurnId)}
            className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs font-semibold text-primary hover:bg-primary/10 disabled:opacity-40"
          >
            <Plus className="h-3.5 w-3.5" /> New
          </button>
        </div>
        <div className="custom-scrollbar min-h-0 flex-1 space-y-1 overflow-y-auto">
          {loading && <p className="px-2 text-xs text-slate-400">Loading sessions…</p>}
          {!loading && recentSessions.length === 0 && <p className="px-2 text-xs italic text-slate-400">No Agent sessions yet</p>}
          {recentSessions.map(session => (
            <button
              key={session.id}
              onClick={() => void selectSession(session)}
              disabled={Boolean(state.activeTurnId)}
              className={`w-full rounded-lg px-2 py-2 text-left text-xs transition-colors ${
                state.session?.id === session.id
                  ? 'bg-primary/10 font-medium text-primary'
                  : 'text-slate-600 hover:bg-slate-50 disabled:opacity-40'
              }`}
            >
              <span className="block truncate">{session.title || 'Untitled conversation'}</span>
              <span className="mt-0.5 block truncate text-[10px] opacity-60">{session.provider} · {session.status}</span>
            </button>
          ))}
        </div>
        <button
          onClick={() => setLegacyMode(true)}
          className="mt-3 border-t border-slate-100 pt-3 text-left text-[11px] text-slate-400 hover:text-slate-700"
        >
          Open legacy chat <ChevronRight className="inline h-3 w-3" />
        </button>
      </aside>

      <section className="glass-card flex min-w-0 flex-1 flex-col p-4">
        <div className="mb-3 flex items-end gap-2 border-b border-slate-100 pb-3">
          <label className="min-w-0 flex-1 text-[11px] font-medium text-slate-500">
            Workspace
            <span className="relative mt-1 flex">
              <FolderGit2 className="pointer-events-none absolute left-2.5 top-2.5 h-3.5 w-3.5 text-slate-400" />
              <select
                aria-label="Workspace"
                value={workspace}
                disabled={Boolean(state.session) || Boolean(state.activeTurnId)}
                onChange={event => {
                  setWorkspace(event.target.value);
                  const project = projects.find(item => item.path === event.target.value);
                  if (project) setCurrentGroup(project.group);
                }}
                className="w-full rounded-lg border border-slate-200 bg-white py-2 pl-8 pr-8 text-xs outline-none focus:border-primary disabled:opacity-60"
              >
                <option value="">Select a registered workspace</option>
                {projects.map(project => <option key={project.path} value={project.path}>{project.path}</option>)}
              </select>
            </span>
          </label>
          <label className="w-40 text-[11px] font-medium text-slate-500">
            Provider
            <select
              aria-label="Provider"
              value={selectedProvider}
              disabled={Boolean(state.session) || Boolean(state.activeTurnId)}
              onChange={event => setSelectedProvider(event.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs outline-none focus:border-primary disabled:opacity-60"
            >
              <option value="">No provider</option>
              {providers.map(provider => (
                <option key={provider.providerId} value={provider.providerId} disabled={!provider.available}>
                  {provider.displayName}{provider.available ? '' : ' (unavailable)'}
                </option>
              ))}
            </select>
          </label>
          <label className="w-36 text-[11px] font-medium text-slate-500">
            Permission
            <select
              aria-label="Permission mode"
              value={permissionMode}
              disabled={Boolean(state.session) || Boolean(state.activeTurnId)}
              onChange={event => setPermissionMode(event.target.value as PermissionMode)}
              className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs outline-none focus:border-primary disabled:opacity-60"
            >
              <option value="workspace-write">Workspace write</option>
              <option value="read-only">Read only</option>
            </select>
          </label>
          <span
            title={connected ? 'Structured Gateway connected' : 'Gateway not connected'}
            className={`mb-0.5 flex items-center gap-1 rounded-lg border px-2 py-2 text-[10px] font-semibold ${
              connected
                ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                : 'border-slate-200 bg-slate-50 text-slate-500'
            }`}
          >
            {connected ? <Wifi className="h-3 w-3" /> : <WifiOff className="h-3 w-3" />}
            {connecting ? 'Connecting' : connected ? 'Interactive' : 'Offline'}
          </span>
          <button
            aria-label="Open activity"
            title="Open activity"
            onClick={() => setShowActivity(true)}
            className="mb-0.5 rounded-lg border border-slate-200 p-2 text-slate-500 hover:bg-slate-50"
          >
            <Activity className="h-4 w-4" />
          </button>
        </div>

        {projects.length === 0 && (
          <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
            Register a workspace before starting an Agent session.{' '}
            <Link to="/settings/workspace" className="font-semibold underline">Open Workspace settings</Link>
          </div>
        )}
        {noGatewayProvider && (
          <div className="mb-3 flex items-start justify-between gap-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
            <div>
              <p className="font-semibold">No interactive provider is available</p>
              <p className="mt-0.5">{providers[0]?.unavailableReason || 'The Agent Gateway could not start.'}</p>
            </div>
            <button className="shrink-0 font-semibold underline" onClick={() => setLegacyMode(true)}>Use legacy chat</button>
          </div>
        )}
        {selectedCapabilities?.available && (
          <div className="mb-3 flex items-center gap-2 rounded-lg border border-cyan-100 bg-cyan-50/60 px-3 py-2 text-[11px] text-cyan-900">
            <ShieldCheck className="h-3.5 w-3.5" />
            Structured session · resume {selectedCapabilities.supportsResume ? 'on' : 'off'} · approvals {selectedCapabilities.supportsApprovals ? 'on' : 'off'} · cancel {selectedCapabilities.supportsCancel ? 'on' : 'off'}
          </div>
        )}
        {error && (
          <div className="mb-3 flex items-center justify-between gap-3 rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-xs text-red-700">
            <span className="flex items-center gap-2"><AlertCircle className="h-3.5 w-3.5 shrink-0" /> {error}</span>
            {state.session && !connected && (
              <button
                className="shrink-0 font-semibold underline"
                onClick={() => void connect(state.session as AgentSession, state.lastSequence, false)}
              >Reconnect</button>
            )}
          </div>
        )}

        <div ref={scrollRef} className="custom-scrollbar min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
          {state.messages.length === 0 && !state.activeTurnId && (
            <div className="flex h-full min-h-48 flex-col items-center justify-center text-center text-slate-400">
              <Bot className="mb-3 h-8 w-8 text-slate-300" />
              <p className="text-sm font-medium text-slate-600">Interactive Agent workspace</p>
              <p className="mt-1 max-w-md text-xs">Choose a workspace and provider. Tool calls, approvals, cancellation, and reconnects stay in one session.</p>
            </div>
          )}
          {state.messages.map(message => (
            <div
              key={message.id}
              className={`max-w-[85%] rounded-xl px-4 py-2.5 text-sm ${
                message.role === 'user'
                  ? 'ml-auto bg-primary/10 text-slate-800'
                  : message.role === 'error'
                    ? 'border border-red-100 bg-red-50 text-red-700'
                    : 'border border-slate-100 bg-slate-50 text-slate-700'
              }`}
            >
              {message.role === 'assistant'
                ? <ReactMarkdown>{message.text || '…'}</ReactMarkdown>
                : <span className="whitespace-pre-wrap">{message.text}</span>}
            </div>
          ))}
          {state.activeTurnId && !state.messages.some(message => message.pending) && (
            <div className="flex max-w-[85%] items-center gap-2 rounded-xl border border-slate-100 bg-slate-50 px-4 py-2.5 text-sm text-slate-400">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Working…
            </div>
          )}
        </div>

        {state.approvals.map(approval => (
          <div key={approval.id} className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-950">
            <p className="font-semibold">Approval required</p>
            {approval.reason && <p className="mt-1 text-amber-800">{approval.reason}</p>}
            {approval.command && <pre className="mt-2 overflow-x-auto rounded-lg bg-slate-900 p-2 text-[11px] text-slate-100">{approval.command}</pre>}
            {approval.cwd && <p className="mt-1 break-all text-[10px] text-amber-700">Working directory: {approval.cwd}</p>}
            <div className="mt-2 flex justify-end gap-2">
              <button onClick={() => respondApproval(approval.id, 'decline')} className="rounded-lg border border-amber-300 px-3 py-1.5 font-semibold hover:bg-amber-100">Decline</button>
              <button onClick={() => respondApproval(approval.id, 'accept')} className="rounded-lg bg-primary px-3 py-1.5 font-semibold text-white hover:bg-primary/90">Approve once</button>
            </div>
          </div>
        ))}

        <div className="mt-3 flex items-end gap-2">
          <textarea
            ref={composerRef}
            value={input}
            rows={1}
            disabled={Boolean(state.activeTurnId) || noGatewayProvider}
            onChange={event => {
              setInput(event.target.value);
              event.target.style.height = 'auto';
              event.target.style.height = `${Math.min(event.target.scrollHeight, 160)}px`;
            }}
            onKeyDown={event => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                void send();
              }
            }}
            placeholder="Message the agent… (Enter to send, Shift+Enter for newline)"
            className="max-h-40 min-h-10 flex-1 resize-none overflow-y-auto rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-primary disabled:opacity-50"
          />
          {state.activeTurnId ? (
            <button
              onClick={cancel}
              disabled={!state.session?.capabilitySnapshot.supportsCancel}
              aria-label="Cancel turn"
              className="rounded-lg border border-red-200 bg-red-50 p-2.5 text-red-600 hover:bg-red-100 disabled:opacity-40"
            >
              <Square className="h-4 w-4 fill-current" />
            </button>
          ) : (
            <button
              onClick={() => void send()}
              disabled={!input.trim() || !workspace || !selectedProvider || connecting || noGatewayProvider}
              aria-label="Send message"
              className="rounded-lg bg-primary p-2.5 text-white hover:bg-primary/90 disabled:opacity-40"
            >
              <Send className="h-4 w-4" />
            </button>
          )}
        </div>
      </section>

      {showActivity && (
        <aside className="glass-card flex w-80 shrink-0 flex-col p-4">
          <div className="mb-3 flex items-center justify-between border-b border-slate-100 pb-3">
            <div>
              <p className="text-sm font-semibold text-slate-800">Activity</p>
              <p className="text-[10px] text-slate-400">Tools, diffs, usage, and protocol events</p>
            </div>
            <button aria-label="Close activity" onClick={() => setShowActivity(false)} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-50"><X className="h-4 w-4" /></button>
          </div>
          <div className="custom-scrollbar min-h-0 flex-1 space-y-2 overflow-y-auto">
            {state.activity.length === 0 && <p className="text-xs italic text-slate-400">No activity yet</p>}
            {state.activity.map(event => (
              <details key={event.sequence} className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2 text-xs">
                <summary className="cursor-pointer font-medium text-slate-700">#{event.sequence} {event.type}</summary>
                <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap text-[10px] text-slate-500">{JSON.stringify(event.data, null, 2)}</pre>
              </details>
            ))}
          </div>
        </aside>
      )}
    </div>
  );
}
