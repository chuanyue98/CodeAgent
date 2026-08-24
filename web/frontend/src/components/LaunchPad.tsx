import { useEffect, useState } from 'react';
import { AlertTriangle, TerminalSquare, X } from 'lucide-react';
import { fetchPtyStatus } from '../api/pty';
import { useProject } from '../context/ProjectContext';
import { useT } from '../i18n/context';
import type { TranslationKey } from '../i18n/locales/en';
import BrowserTerminal from './BrowserTerminal';

interface Engine {
  id: string;
  name?: string;
  /** 非品牌名称（如纯终端）走 i18n。 */
  nameKey?: TranslationKey;
  /** Brand blurb that stays as-is (product names), or a key when it is prose. */
  description?: string;
  descriptionKey?: TranslationKey;
  color: string;
}

// Engine names and their vendor blurbs are brands, so they are not translated;
// only OpenCode's descriptive line is prose, and it carries a key instead.
const ENGINES: Engine[] = [
  { id: 'claude',    name: 'Claude',    description: 'Anthropic · Claude Code CLI',      color: 'bg-orange-50 border-orange-200 text-orange-700' },
  { id: 'opencode',  name: 'OpenCode',  descriptionKey: 'launch.opencodeDescription', color: 'bg-violet-50 border-violet-200 text-violet-700' },
  { id: 'codex',     name: 'Codex',     description: 'OpenAI · Codex CLI',               color: 'bg-emerald-50 border-emerald-200 text-emerald-700' },
  { id: 'codebuddy', name: 'CodeBuddy', description: 'Tencent · CodeBuddy Code CLI',     color: 'bg-sky-50 border-sky-200 text-sky-700' },
  { id: 'shell',     nameKey: 'launch.shellName', descriptionKey: 'launch.shellDescription', color: 'bg-slate-50 border-slate-200 text-slate-700' },
];

export default function LaunchPad() {
  const t = useT();
  const {
    validProjects,
    selectedWorkspace,
    setSelectedWorkspace,
  } = useProject();

  const [available, setAvailable] = useState<boolean | null>(null);
  const [reason, setReason] = useState<string | null>(null);
  const [activeSession, setActiveSession] = useState<{ engine: string; cwd: string } | null>(null);

  useEffect(() => {
    fetchPtyStatus()
      .then(status => {
        setAvailable(status.available);
        setReason(status.reason);
      })
      .catch(err => {
        setAvailable(false);
        setReason(err instanceof Error ? err.message : t('launch.detectFailed'));
      });
  }, [t]);

  const effectiveProject = validProjects.some(project => project.path === selectedWorkspace)
    ? selectedWorkspace
    : (validProjects[0]?.path ?? '');

  if (activeSession) {
    return (
      <div className="flex h-full min-h-0 flex-col gap-2">
        <div className="flex shrink-0 items-center justify-between">
          <div className="text-sm font-medium text-slate-700">
            {(() => {
              const engine = ENGINES.find(item => item.id === activeSession.engine);
              return engine ? (engine.nameKey ? t(engine.nameKey) : engine.name) : activeSession.engine;
            })()} · {activeSession.cwd}
          </div>
          <button
            onClick={() => setActiveSession(null)}
            className="flex items-center gap-1 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
          >
            <X size={14} /> {t('launch.closeTerminal')}
          </button>
        </div>
        <BrowserTerminal
          engine={activeSession.engine}
          cwd={activeSession.cwd}
          onExit={() => {}}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <p className="text-sm text-slate-600">
          {t('launch.intro')}
        </p>
        <p className="text-xs text-slate-400">
          {t('launch.introDetail')}
        </p>
      </div>

      {available === false && (
        <div role="status" className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <p className="font-semibold">{t('launch.unavailable')}</p>
            <p className="mt-0.5 text-xs">{reason}</p>
          </div>
        </div>
      )}

      {validProjects.length === 0 ? (
        <div role="status" className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
          {t('launch.registerFirst')}
        </div>
      ) : (
        <div className="max-w-sm space-y-1">
          <label htmlFor="launchpad-project" className="text-xs font-medium text-slate-500">{t('filters.workspace')}</label>
          <select
            id="launchpad-project"
            value={effectiveProject}
            onChange={event => setSelectedWorkspace(event.target.value)}
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
          >
            {validProjects.map(project => (
              <option key={project.path} value={project.path}>{project.path}</option>
            ))}
          </select>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {ENGINES.map((engine) => (
          <div
            key={engine.id}
            className="glass-card p-6 flex items-center justify-between gap-4"
          >
            <div className="space-y-1">
              <div className="font-semibold text-slate-800">{engine.nameKey ? t(engine.nameKey) : engine.name}</div>
              <div className="text-xs text-slate-500">{engine.descriptionKey ? t(engine.descriptionKey) : engine.description}</div>
            </div>

            <button
              onClick={() => setActiveSession({ engine: engine.id, cwd: effectiveProject })}
              disabled={!available || !effectiveProject}
              className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium border transition-all
                ${!available || !effectiveProject
                  ? 'opacity-50 cursor-not-allowed'
                  : 'hover:scale-105 active:scale-95 cursor-pointer'}
                ${engine.color}`}
            >
              <TerminalSquare size={15} />
              {t('launch.openTerminal')}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
