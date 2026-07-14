import { useEffect, useState } from 'react';
import { AlertTriangle, ExternalLink, Loader2 } from 'lucide-react';
import request from '../utils/request';

interface Engine {
  id: string;
  name: string;
  description: string;
  color: string;
}

interface LaunchCapability {
  available: boolean;
  terminal: string | null;
  mode: 'local_gui';
  reason?: string | null;
}

interface LaunchResult {
  status: 'launched';
  engine: string;
  terminal: string;
}

const ENGINES: Engine[] = [
  { id: 'claude',    name: 'Claude',    description: 'Anthropic · 高推理能力',         color: 'bg-orange-50 border-orange-200 text-orange-700' },
  { id: 'gemini',    name: 'Gemini',    description: 'Google · 多模态支持',             color: 'bg-blue-50 border-blue-200 text-blue-700' },
  { id: 'opencode',  name: 'OpenCode',  description: 'Local npm · TUI 交互体验',        color: 'bg-violet-50 border-violet-200 text-violet-700' },
  { id: 'codex',     name: 'Codex',     description: 'OpenAI · Codex CLI',              color: 'bg-emerald-50 border-emerald-200 text-emerald-700' },
];

export default function LaunchPad() {
  const [launching, setLaunching] = useState<string | null>(null);
  const [lastLaunched, setLastLaunched] = useState<string | null>(null);
  const [lastTerminal, setLastTerminal] = useState<string | null>(null);
  const [capability, setCapability] = useState<LaunchCapability | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    request<LaunchCapability>('/api/launch/status')
      .then(setCapability)
      .catch(err => setError(err instanceof Error ? err.message : 'Failed to detect local terminal support'));
  }, []);

  async function launch(engine: string) {
    setLaunching(engine);
    setError(null);
    try {
      const result = await request<LaunchResult>(`/api/launch/${engine}`, { method: 'POST' });
      setLastLaunched(engine);
      setLastTerminal(result.terminal);
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Failed to open local terminal');
    } finally {
      setLaunching(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <p className="text-sm text-slate-600">
          Opens the provider CLI in a separate terminal window on the machine running CodeAgent.
        </p>
        <p className="text-xs text-slate-400">This is a local launcher, not an in-browser terminal.</p>
      </div>

      {capability && !capability.available && (
        <div role="status" className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <p className="font-semibold">Local terminal unavailable</p>
            <p className="mt-0.5 text-xs">{capability.reason}</p>
          </div>
        </div>
      )}

      {error && (
        <div role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {ENGINES.map((engine) => (
          <div
            key={engine.id}
            className="glass-card p-6 flex items-center justify-between gap-4"
          >
            <div className="space-y-1">
              <div className="font-semibold text-slate-800">{engine.name}</div>
              <div className="text-xs text-slate-500">{engine.description}</div>
              {lastLaunched === engine.id && (
                <div className="text-xs text-emerald-600 font-medium">Opened in {lastTerminal}</div>
              )}
            </div>

            <button
              onClick={() => launch(engine.id)}
              disabled={launching !== null || !capability?.available}
              className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium border transition-all
                ${launching !== null || !capability?.available
                  ? 'opacity-50 cursor-not-allowed'
                  : 'hover:scale-105 active:scale-95 cursor-pointer'}
                ${engine.color}`}
            >
              {launching === engine.id ? <Loader2 size={15} className="animate-spin" /> : <ExternalLink size={15} />}
              {launching === engine.id ? 'Opening…' : 'Open terminal'}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
