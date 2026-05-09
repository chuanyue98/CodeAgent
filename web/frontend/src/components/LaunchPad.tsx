import { useState } from 'react';
import { Terminal } from 'lucide-react';

interface Engine {
  id: string;
  name: string;
  description: string;
  color: string;
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

  async function launch(engine: string) {
    setLaunching(engine);
    try {
      await fetch(`/api/launch/${engine}`, { method: 'POST' });
      setLastLaunched(engine);
    } finally {
      setLaunching(null);
    }
  }

  return (
    <div className="space-y-6">
      <p className="text-sm text-slate-500">选择引擎，点击启动即可在新终端窗口中运行对应的 ca 会话。</p>

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
                <div className="text-xs text-emerald-600 font-medium">已启动 ✓</div>
              )}
            </div>

            <button
              onClick={() => launch(engine.id)}
              disabled={launching === engine.id}
              className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium border transition-all
                ${launching === engine.id
                  ? 'opacity-50 cursor-not-allowed'
                  : 'hover:scale-105 active:scale-95 cursor-pointer'}
                ${engine.color}`}
            >
              <Terminal size={15} />
              {launching === engine.id ? '启动中…' : '启动'}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
