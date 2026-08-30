import { useState } from 'react';
import { ArrowLeft, BookOpen, CheckCircle2, Circle, Clock, Code, GitBranch, History, Pencil, Play, StopCircle, Terminal, Trash2 } from 'lucide-react';
import LogViewer from '../LogViewer';
import ConfirmDialog from '../shared/ConfirmDialog';
import EditTaskModal from './EditTaskModal';
import RunChanges from './RunChanges';
import { classifyStageStatus, type Engine, type RunStatus, type Task } from './types';
import { useT } from '../../i18n/context';
import request from '../../utils/request';

function stageIcon(status: string) {
  const state = classifyStageStatus(status);
  if (state === 'done')
    return <div className="p-2 bg-primary/10 rounded-xl"><CheckCircle2 className="w-4 h-4 text-primary" /></div>;
  if (state === 'wip')
    return <div className="p-2 bg-amber-50 rounded-xl"><Clock className="w-4 h-4 text-amber-500 animate-spin-slow" /></div>;
  return <div className="p-2 bg-slate-100 rounded-xl"><Circle className="w-4 h-4 text-slate-300" /></div>;
}

function stageBadge(status: string) {
  const state = classifyStageStatus(status);
  if (state === 'done')
    return 'border-primary/20 text-primary bg-primary/10';
  if (state === 'wip')
    return 'border-amber-200 text-amber-600 bg-amber-50 animate-pulse';
  return 'border-slate-100 text-slate-400 bg-slate-50';
}

/** Formats a duration in seconds as a compact human string (e.g. "12s", "3m 4s"). */
function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '—';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
}

function runDuration(run: RunStatus): number {
  const end = run.endTime ?? (run.status === 'running' ? Date.now() / 1000 : 0);
  return end ? end - run.startTime : 0;
}

function runBadgeClass(status: RunStatus['status']): string {
  switch (status) {
    case 'running':
      return 'border-emerald-200 text-emerald-600 bg-emerald-50 animate-pulse';
    case 'completed':
      return 'border-primary/20 text-primary bg-primary/10';
    case 'failed':
      return 'border-red-200 text-red-600 bg-red-50';
    case 'stopped':
      return 'border-slate-200 text-slate-500 bg-slate-50';
    default:
      return 'border-slate-100 text-slate-400 bg-slate-50';
  }
}

export default function TaskDetail({
  task,
  engines,
  activeRun,
  runHistory,
  onBack,
  onRun,
  onStop,
  onDeleted,
  onTaskUpdated,
  workspace,
  projects,
  onWorkspaceChange,
}: {
  task: Task;
  engines: Engine[];
  activeRun?: RunStatus;
  runHistory: RunStatus[];
  onBack: () => void;
  onRun: (engine: string) => void;
  onStop: (id: string) => void;
  onDeleted: () => void;
  onTaskUpdated: (updated: Task) => void;
  workspace: string;
  projects: { path: string; group: string; available?: boolean }[];
  onWorkspaceChange: (workspace: string) => void;
}) {
  const t = useT();
  const [selectedEngine, setSelectedEngine] = useState(engines[0]?.id || 'opencode');
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  // Which run's log to display in the LogViewer. Defaults to the active run;
  // clicking a history entry swaps it to inspect that run's log.
  const [viewedLogId, setViewedLogId] = useState<string | null>(null);
  const [logTab, setLogTab] = useState<'logs' | 'changes'>('logs');

  // Reset the viewed log whenever the selected task changes so a stale id
  // from a previous task doesn't leak into the LogViewer. Adjusting state
  // during render (rather than in an effect) avoids the cascading render the
  // react-hooks/set-state-in-effect rule guards against.
  const [trackedName, setTrackedName] = useState(task.name);
  if (task.name !== trackedName) {
    setTrackedName(task.name);
    setViewedLogId(null);
    setLogTab('logs');
  }

  // While a run is active, always show its live log regardless of what the
  // user previously selected from history.
  const logTaskId = activeRun ? activeRun.taskId : viewedLogId;

  const done = task.stages.filter(s => classifyStageStatus(s.status) === 'done').length;
  const pct = task.stages.length > 0 ? Math.round((done / task.stages.length) * 100) : 0;

  // The most recent run (active first, otherwise the first history entry) is
  // what the metadata row summarizes.
  const metaRun = activeRun ?? runHistory[0];
  const hasPriorRuns = runHistory.length > 0;
  const runLabel = hasPriorRuns ? t('common.retry') : t('taskDetail.run');

  const handleDelete = async () => {
    setDeleteError(null);
    // The backend refuses to delete a task with an active run (409). Surface
    // that as an inline error rather than navigating away.
    try {
      await request(`/api/tasks/${task.name}`, { method: 'DELETE' });
      onDeleted();
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : t('taskDetail.deleteFailed'));
      setConfirmDelete(false);
    }
  };

  return (
    <div className="p-8 max-w-4xl mx-auto space-y-6 pb-20">
      <div className="flex items-center justify-between">
        <button onClick={onBack} className="flex items-center gap-2 text-sm text-slate-500 hover:text-primary transition-colors">
          <ArrowLeft className="w-4 h-4" />
          {t('common.back')}
        </button>

        <div className="flex items-center gap-3">
          <button
            onClick={() => setEditing(true)}
            className="flex items-center gap-2 px-3 py-2 border border-slate-200 text-slate-600 rounded-xl text-sm font-medium hover:bg-slate-50 transition-colors"
          >
            <Pencil className="w-4 h-4" />
            {t('common.edit')}
          </button>
          <button
            onClick={() => setConfirmDelete(true)}
            disabled={!!activeRun}
            title={activeRun ? t('taskDetail.deleteBlocked') : undefined}
            className="flex items-center gap-2 px-3 py-2 border border-red-100 text-red-500 rounded-xl text-sm font-medium hover:bg-red-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <Trash2 className="w-4 h-4" />
            {t('common.delete')}
          </button>

          {activeRun ? (
            <button
              onClick={() => onStop(activeRun.taskId)}
              className="flex items-center gap-2 px-4 py-2 bg-red-50 text-red-600 rounded-xl text-sm font-bold border border-red-100 hover:bg-red-100 transition-colors"
            >
              <StopCircle className="w-4 h-4" />
              {t('taskDetail.stopExecution')}
            </button>
          ) : (
            <>
              <select
                aria-label={t('filters.workspace')}
                value={workspace}
                onChange={e => onWorkspaceChange(e.target.value)}
                className="max-w-56 bg-white border border-slate-200 rounded-xl px-3 py-2 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-primary/20"
              >
                <option value="" disabled>{t('taskDetail.selectWorkspace')}</option>
                {projects.filter(project => project.available !== false).map(project => (
                  <option key={project.path} value={project.path}>{project.path}</option>
                ))}
              </select>
              <select
                value={selectedEngine}
                onChange={(e) => setSelectedEngine(e.target.value)}
                className="bg-white border border-slate-200 rounded-xl px-3 py-2 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-primary/20"
              >
                {engines.map(e => (
                  <option key={e.id} value={e.id}>{e.name}</option>
                ))}
              </select>
              <button
                onClick={() => onRun(selectedEngine)}
                className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-xl text-sm font-bold shadow-lg shadow-primary/20 hover:scale-105 active:scale-95 transition-all"
              >
                <Play className="w-4 h-4" />
                {runLabel}
              </button>
            </>
          )}
        </div>
      </div>

      {deleteError && (
        <div className="p-3 bg-red-50 border border-red-100 text-red-600 rounded-xl text-sm">
          {deleteError}
        </div>
      )}

      <div className="flex justify-between items-start">
        <div className="flex-1">
          <h2 className="text-2xl font-semibold tracking-tight text-slate-900 flex items-center gap-3">
            {task.title}
            {activeRun && (
              <span className="flex items-center gap-1.5 px-3 py-1 bg-emerald-50 text-emerald-600 rounded-full text-xs font-bold uppercase tracking-wider border border-emerald-100 animate-pulse">
                {t('taskDetail.running')}
              </span>
            )}
          </h2>
          {task.description && <p className="text-sm text-slate-500 mt-1">{task.description}</p>}
        </div>
      </div>

      {/* Run metadata: summarizes the active or most-recent run. */}
      {metaRun && (
        <div className="glass-card p-4 border-slate-100 flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
          <span className="flex items-center gap-2">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{t('filters.engine')}</span>
            <span className="font-medium text-slate-700">{metaRun.engine}</span>
          </span>
          <span className="flex items-center gap-2">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{t('taskDetail.duration')}</span>
            <span className="font-medium text-slate-700">{formatDuration(runDuration(metaRun))}</span>
          </span>
          {metaRun.exitCode !== undefined && metaRun.exitCode !== null && (
            <span className="flex items-center gap-2">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{t('taskDetail.exitCode')}</span>
              <span className="font-mono font-medium text-slate-700">{metaRun.exitCode}</span>
            </span>
          )}
          <span className={`text-[10px] px-2.5 py-1 rounded-lg font-bold uppercase tracking-wider border ${runBadgeClass(metaRun.status)}`}>
            {metaRun.status}
          </span>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          {task.hasStages && (
            <>
              <section className="glass-card p-6 space-y-4 border-slate-100">
                <div className="flex justify-between items-end">
                  <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{t('taskDetail.progress')}</span>
                  <span className="text-3xl font-semibold text-primary tracking-tighter">{pct}%</span>
                </div>
                <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
                  <div className="h-full bg-primary rounded-full transition-all duration-700" style={{ width: `${pct}%` }} />
                </div>
                <p className="text-xs text-slate-400">{t('taskDetail.stagesDone', { done, total: task.stages.length })}</p>
              </section>

              <section className="space-y-3">
                <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wider">{t('taskDetail.stages')}</h2>
                {task.stages.map((stage, i) => (
                  <div
                    key={i}
                    className={`glass-card p-5 flex items-start gap-4 border transition-all ${
                      classifyStageStatus(stage.status) === 'wip'
                        ? 'border-amber-200/60 bg-amber-50/30'
                        : 'border-slate-100'
                    }`}
                  >
                    <div className="flex-shrink-0 mt-0.5">{stageIcon(stage.status)}</div>
                    <div className="flex-1 min-w-0">
                      <div className="flex justify-between items-start gap-2">
                        <h3 className="font-medium text-slate-900 text-sm">{stage.name}</h3>
                        {stage.status && (
                          <span className={`text-[10px] px-2.5 py-1 rounded-lg font-bold uppercase tracking-wider border flex-shrink-0 ${stageBadge(stage.status)}`}>
                            {stage.status}
                          </span>
                        )}
                      </div>
                      {stage.goal && <p className="text-xs text-slate-500 mt-1">{stage.goal}</p>}
                    </div>
                  </div>
                ))}
              </section>
            </>
          )}

          {logTaskId && (
            <section className="space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wider flex items-center gap-2">
                  {logTab === 'logs' ? <Terminal className="w-4 h-4" /> : <GitBranch className="w-4 h-4" />}
                  {logTab === 'logs' ? t('taskDetail.logs') : t('taskDetail.changes')}
                </h2>
                <div className="flex rounded-lg border border-slate-200 overflow-hidden text-xs font-semibold">
                  <button
                    onClick={() => setLogTab('logs')}
                    className={`px-3 py-1.5 transition-colors ${
                      logTab === 'logs' ? 'bg-primary/10 text-primary' : 'bg-white text-slate-500 hover:bg-slate-50'
                    }`}
                  >
                    {t('taskDetail.tabLogs')}
                  </button>
                  <button
                    onClick={() => setLogTab('changes')}
                    className={`px-3 py-1.5 transition-colors ${
                      logTab === 'changes' ? 'bg-primary/10 text-primary' : 'bg-white text-slate-500 hover:bg-slate-50'
                    }`}
                  >
                    {t('taskDetail.tabChanges')}
                  </button>
                </div>
              </div>
              <div className="rounded-xl overflow-hidden border border-slate-200" style={{ height: 400 }}>
                {logTab === 'logs' ? (
                  <LogViewer taskId={logTaskId} />
                ) : (
                  <RunChanges taskId={logTaskId} />
                )}
              </div>
            </section>
          )}

          {!task.hasStages && task.content && !logTaskId && (
            <section className="glass-card p-6 border-slate-100">
              <pre className="text-sm text-slate-700 whitespace-pre-wrap font-sans leading-relaxed">{task.content}</pre>
            </section>
          )}
        </div>

        <div className="space-y-6">
          <section className="space-y-3">
            <h2 className="text-xs font-bold text-slate-400 uppercase tracking-widest flex items-center gap-2">
              <Terminal className="w-3.5 h-3.5" />
              {t('taskDetail.mountedSkills')}
            </h2>
            <div className="space-y-2">
              {task.resolvedSkills && task.resolvedSkills.length > 0 ? (
                task.resolvedSkills.map(skill => (
                  <div key={skill.id} className="glass-card p-4 border-slate-100 space-y-2">
                    <div className="flex items-center gap-2">
                      <Code className="w-4 h-4 text-primary" />
                      <span className="text-sm font-semibold text-slate-900">{skill.name}</span>
                    </div>
                    {skill.description && <p className="text-xs text-slate-500 line-clamp-2">{skill.description}</p>}
                    {skill.scripts && skill.scripts.length > 0 && (
                      <div className="pt-2 flex flex-wrap gap-1.5">
                        {skill.scripts.map(s => (
                          <span key={s} className="px-1.5 py-0.5 bg-slate-100 text-slate-500 rounded text-[10px] font-mono">
                            {s}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))
              ) : (
                <div className="text-xs text-slate-400 italic p-4 bg-slate-50 rounded-xl border border-dashed border-slate-200">
                  {t('taskDetail.noSkills')}
                </div>
              )}
            </div>
          </section>

          <section className="space-y-3">
            <h2 className="text-xs font-bold text-slate-400 uppercase tracking-widest flex items-center gap-2">
              <BookOpen className="w-3.5 h-3.5" />
              {t('taskDetail.injectedPrompts')}
            </h2>
            <div className="flex flex-wrap gap-2">
              {task.resolvedPrompts && task.resolvedPrompts.length > 0 ? (
                task.resolvedPrompts.map(prompt => (
                  <span key={prompt} className="px-2 py-1 bg-primary/5 text-primary border border-primary/10 rounded-lg text-xs font-medium">
                    {prompt}
                  </span>
                ))
              ) : (
                <div className="text-xs text-slate-400 italic p-4 bg-slate-50 rounded-xl border border-dashed border-slate-200 w-full">
                  {t('taskDetail.noPrompts')}
                </div>
              )}
            </div>
          </section>

          {/* Run history: every run for this task in the current server session. */}
          <section className="space-y-3">
            <h2 className="text-xs font-bold text-slate-400 uppercase tracking-widest flex items-center gap-2">
              <History className="w-3.5 h-3.5" />
              {t('taskDetail.runHistory')}
            </h2>
            {runHistory.length > 0 ? (
              <div className="space-y-2">
                {runHistory.map(run => {
                  const isActive = activeRun?.taskId === run.taskId;
                  const isViewed = viewedLogId === run.taskId;
                  return (
                    <button
                      key={run.taskId}
                      onClick={() => setViewedLogId(run.taskId)}
                      className={`w-full text-left glass-card p-3 border transition-all flex items-center justify-between gap-3 ${
                        isActive || isViewed ? 'border-primary/30 bg-primary/5' : 'border-slate-100 hover:bg-slate-50/50'
                      }`}
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-slate-800 truncate">{run.engine}</span>
                          <span className={`text-[10px] px-2 py-0.5 rounded-lg font-bold uppercase tracking-wider border ${runBadgeClass(run.status)}`}>
                            {run.status}
                          </span>
                        </div>
                        <p className="text-[11px] text-slate-400 mt-0.5">
                          {new Date(run.startTime * 1000).toLocaleString()} · {formatDuration(runDuration(run))}
                          {run.exitCode !== undefined && run.exitCode !== null && ` · ${t('taskDetail.exitCode')} ${run.exitCode}`}
                        </p>
                      </div>
                      {(isActive || isViewed) && <Terminal className="w-3.5 h-3.5 text-primary shrink-0" />}
                    </button>
                  );
                })}
              </div>
            ) : (
              <div className="text-xs text-slate-400 italic p-4 bg-slate-50 rounded-xl border border-dashed border-slate-200">
                {t('taskDetail.noRuns')}
              </div>
            )}
          </section>
        </div>
      </div>

      {editing && (
        <EditTaskModal
          task={task}
          onClose={() => setEditing(false)}
          onSaved={updated => {
            setEditing(false);
            onTaskUpdated(updated);
          }}
        />
      )}

      {confirmDelete && (
        <ConfirmDialog
          title={t('taskDetail.confirmDeleteTitle')}
          description={t('taskDetail.confirmDeleteDescription', { name: task.title })}
          confirmLabel={t('common.delete')}
          onConfirm={() => void handleDelete()}
          onCancel={() => setConfirmDelete(false)}
        />
      )}
    </div>
  );
}
