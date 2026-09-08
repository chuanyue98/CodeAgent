import { useState } from 'react';
import { useNavigate } from 'react-router';
import {
  ArrowLeft,
  BookOpen,
  CheckCircle2,
  Circle,
  Clock,
  Code,
  GitBranch,
  History,
  Layers,
  Pencil,
  Play,
  StopCircle,
  Terminal,
  Trash2,
} from 'lucide-react';
import LogViewer from '../LogViewer';
import ConfirmDialog from '../shared/ConfirmDialog';
import StatusDot from '../shared/StatusDot';
import EditTaskModal from './EditTaskModal';
import RunChanges from './RunChanges';
import TaskBlueprintView from './TaskBlueprintView';
import { formatWorkspaceLabel } from '../../utils/workspaceFormat';
import { classifyStageStatus, type Engine, type RunStatus, type Task } from './types';
import { useLanguageCode, useT } from '../../i18n/context';
import { fetchSchedules } from '../../api/schedules';
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
    return 'border-amber-200 text-amber-600 bg-amber-50';
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
      return 'border-emerald-200 text-emerald-600 bg-emerald-50';
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

function useSafeNavigate() {
  try {
    return useNavigate();
  } catch {
    return (path: string) => {
      if (typeof window !== 'undefined') {
        window.location.href = path;
      }
    };
  }
}

type StudioTab = 'blueprint' | 'logs' | 'changes' | 'history';

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
  const lang = useLanguageCode();
  const navigate = useSafeNavigate();

  const [selectedEngine, setSelectedEngine] = useState(engines[0]?.id || 'opencode');
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [linkedScheduleCount, setLinkedScheduleCount] = useState(0);

  // Tab state
  const [activeTab, setActiveTab] = useState<StudioTab>(() => (activeRun ? 'logs' : 'blueprint'));

  // Which run's log to display in the LogViewer. Defaults to the active run;
  // clicking a history entry swaps it to inspect that run's log.
  const [viewedLogId, setViewedLogId] = useState<string | null>(null);

  // Automatically activate the logs tab when a new run begins
  const [prevActiveRunId, setPrevActiveRunId] = useState<string | undefined>(activeRun?.taskId);
  if (activeRun?.taskId !== prevActiveRunId) {
    setPrevActiveRunId(activeRun?.taskId);
    if (activeRun) {
      setActiveTab('logs');
    }
  }

  // Reset the viewed log and active tab whenever the selected task changes
  const [trackedName, setTrackedName] = useState(task.name);
  if (task.name !== trackedName) {
    setTrackedName(task.name);
    setViewedLogId(null);
    setActiveTab(activeRun ? 'logs' : 'blueprint');
  }

  // While a run is active, always show its live log regardless of what the
  // user previously selected from history.
  const logTaskId = activeRun ? activeRun.taskId : viewedLogId;

  const done = task.stages.filter(s => classifyStageStatus(s.status) === 'done').length;
  const pct = task.stages.length > 0 ? Math.round((done / task.stages.length) * 100) : 0;

  // The most recent run (active first, otherwise the first history entry) is
  // what the metadata card summarizes.
  const metaRun = activeRun ?? runHistory[0];
  const hasPriorRuns = runHistory.length > 0;
  const runLabel = hasPriorRuns ? t('common.retry') : t('taskDetail.run');

  const goToSchedule = () => {
    const params = new URLSearchParams();
    params.set('task', task.name);
    if (workspace) params.set('workspace', workspace);
    if (selectedEngine) params.set('engine', selectedEngine);
    navigate(`/automations/schedules?${params.toString()}`);
  };

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

  const initiateDelete = async () => {
    try {
      const schedules = await fetchSchedules();
      const linked = schedules.filter(s => s.taskName === task.name && s.enabled);
      setLinkedScheduleCount(linked.length);
    } catch {
      setLinkedScheduleCount(0);
    }
    setConfirmDelete(true);
  };

  return (
    <div className="p-6 lg:p-8 w-full space-y-6 pb-16">
      {/* Studio Header */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b border-slate-200/70 pb-6">
        {/* Left: Breadcrumbs, Title, Active Badge, Description */}
        <div className="space-y-1.5 min-w-0">
          <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
            <button
              onClick={onBack}
              className="flex items-center gap-1.5 text-slate-500 hover:text-primary transition-colors py-0.5 px-1.5 -ml-1.5 rounded-lg hover:bg-slate-100"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>{t('common.back')}</span>
            </button>
            <span className="text-slate-300">/</span>
            <span className="font-mono text-slate-400 truncate">{task.name}</span>
          </div>

          <div className="flex items-center gap-3 flex-wrap">
            <h2 className="text-2xl font-semibold tracking-tight text-slate-900 flex items-center gap-3">
              {task.title}
            </h2>
            {activeRun && (
              <span className="flex items-center gap-1.5 px-3 py-1 bg-emerald-50 text-emerald-600 rounded-full text-xs font-bold uppercase tracking-wider border border-emerald-100">
                <StatusDot tone="running" pulse />
                {t('taskDetail.running')}
              </span>
            )}
          </div>

          {task.description && (
            <p className="text-sm text-slate-500 max-w-2xl">{task.description}</p>
          )}
        </div>

        {/* Right: Controls & Secondary Action Toolbar */}
        <div className="flex flex-wrap items-center gap-2.5 shrink-0">
          {activeRun ? (
            <button
              onClick={() => onStop(activeRun.taskId)}
              className="flex items-center gap-2 px-4 py-2 bg-red-50 text-red-600 rounded-xl text-sm font-bold border border-red-200 hover:bg-red-100 transition-colors"
            >
              <StopCircle className="w-4 h-4" />
              {t('taskDetail.stopExecution')}
            </button>
          ) : (
            <>
              <select
                aria-label={t('filters.workspace')}
                value={workspace}
                title={workspace}
                onChange={e => onWorkspaceChange(e.target.value)}
                className="min-w-44 max-w-xs bg-white border border-slate-200 rounded-xl px-3 py-2 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-primary/20 truncate"
              >
                <option value="" disabled>{t('taskDetail.selectWorkspace')}</option>
                {projects.filter(project => project.available !== false).map(project => (
                  <option key={project.path} value={project.path}>
                    {formatWorkspaceLabel(project.path, project.group)}
                  </option>
                ))}
              </select>

              <select
                value={selectedEngine}
                onChange={e => setSelectedEngine(e.target.value)}
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

          {/* Secondary Action Toolset */}
          <div className="flex items-center border-l border-slate-200 pl-2.5 gap-2">
            <button
              onClick={() => setEditing(true)}
              className="flex items-center gap-1.5 px-3 py-2 border border-slate-200 text-slate-600 rounded-xl text-sm font-medium hover:bg-slate-50 transition-colors"
            >
              <Pencil className="w-4 h-4" />
              <span>{t('common.edit')}</span>
            </button>

            <button
              onClick={goToSchedule}
              className="flex items-center gap-1.5 px-3 py-2 border border-slate-200 text-slate-600 rounded-xl text-sm font-medium hover:bg-slate-50 transition-colors"
            >
              <Clock className="w-4 h-4" />
              <span>{t('taskDetail.scheduleThisTask')}</span>
            </button>

            <button
              onClick={() => void initiateDelete()}
              disabled={!!activeRun}
              title={activeRun ? t('taskDetail.deleteBlocked') : undefined}
              className="flex items-center gap-1.5 px-3 py-2 border border-red-100 text-red-500 rounded-xl text-sm font-medium hover:bg-red-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <Trash2 className="w-4 h-4" />
              <span>{t('common.delete')}</span>
            </button>
          </div>
        </div>
      </div>

      {deleteError && (
        <div className="p-3 bg-red-50 border border-red-100 text-red-600 rounded-xl text-sm">
          {deleteError}
        </div>
      )}

      {/* Main Studio 2-Column Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Primary Workspace (8 cols) */}
        <div className="lg:col-span-8 space-y-4">
          {/* Tab Navigation Bar */}
          <div className="flex items-center gap-1 border-b border-slate-200 pb-px mb-6 overflow-x-auto">
            <button
              role="button"
              aria-label={t('taskDetail.tabBlueprint')}
              onClick={() => setActiveTab('blueprint')}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-semibold border-b-2 transition-all whitespace-nowrap ${
                activeTab === 'blueprint'
                  ? 'border-primary text-primary'
                  : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
              }`}
            >
              <Layers className="w-4 h-4" />
              <span>{t('taskDetail.tabBlueprint')}</span>
            </button>

            <button
              role="button"
              aria-label={t('taskDetail.tabLogs')}
              onClick={() => setActiveTab('logs')}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-semibold border-b-2 transition-all whitespace-nowrap ${
                activeTab === 'logs'
                  ? 'border-primary text-primary'
                  : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
              }`}
            >
              <Terminal className="w-4 h-4" />
              <span>{t('taskDetail.tabLogs')}</span>
              {activeRun && <StatusDot tone="running" pulse />}
            </button>

            <button
              role="button"
              aria-label={t('taskDetail.tabChanges')}
              onClick={() => setActiveTab('changes')}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-semibold border-b-2 transition-all whitespace-nowrap ${
                activeTab === 'changes'
                  ? 'border-primary text-primary'
                  : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
              }`}
            >
              <GitBranch className="w-4 h-4" />
              <span>{t('taskDetail.tabChanges')}</span>
            </button>

            <button
              role="button"
              aria-label={t('taskDetail.tabHistory')}
              onClick={() => setActiveTab('history')}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-semibold border-b-2 transition-all whitespace-nowrap ${
                activeTab === 'history'
                  ? 'border-primary text-primary'
                  : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
              }`}
            >
              <History className="w-4 h-4" />
              <span>{t('taskDetail.tabHistory')}</span>
              {runHistory.length > 0 && (
                <span className="px-1.5 py-0.5 bg-slate-100 text-slate-600 rounded-full text-xs font-mono">
                  {runHistory.length}
                </span>
              )}
            </button>
          </div>

          {/* Tab 1: Blueprint View */}
          {activeTab === 'blueprint' && (
            <div className="space-y-6">
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

              {/* Full blueprint markdown / structured view */}
              <TaskBlueprintView content={task.content} title={task.title} />
            </div>
          )}

          {/* Tab 2: Terminal Logs */}
          {activeTab === 'logs' && (
            <div>
              {logTaskId ? (
                <div className="rounded-xl overflow-hidden border border-slate-200" style={{ height: 480 }}>
                  <LogViewer taskId={logTaskId} />
                </div>
              ) : (
                <div className="glass-card p-12 border-dashed border-slate-200 text-center space-y-3">
                  <div className="p-3 bg-slate-100 text-slate-400 rounded-2xl w-fit mx-auto">
                    <Terminal className="w-6 h-6" />
                  </div>
                  <h3 className="text-sm font-semibold text-slate-700">
                    {lang === 'zh' ? '暂无执行日志' : 'No execution logs yet'}
                  </h3>
                  <p className="text-xs text-slate-400 max-w-sm mx-auto">
                    {lang === 'zh'
                      ? '运行此任务或从历史记录中选择一次执行以查看终端日志。'
                      : 'Run this task or select a past run from history to view terminal logs.'}
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Tab 3: Code Changes */}
          {activeTab === 'changes' && (
            <div>
              {logTaskId ? (
                <RunChanges taskId={logTaskId} />
              ) : (
                <div className="glass-card p-12 border-dashed border-slate-200 text-center space-y-3">
                  <div className="p-3 bg-slate-100 text-slate-400 rounded-2xl w-fit mx-auto">
                    <GitBranch className="w-6 h-6" />
                  </div>
                  <h3 className="text-sm font-semibold text-slate-700">
                    {lang === 'zh' ? '暂无变更记录' : 'No changes recorded'}
                  </h3>
                  <p className="text-xs text-slate-400 max-w-sm mx-auto">
                    {lang === 'zh'
                      ? '执行任务后可在此检查文件修改与 Git diff。'
                      : 'Run this task to inspect file modifications and git diffs.'}
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Tab 4: Execution History */}
          {activeTab === 'history' && (
            <div className="space-y-4">
              {runHistory.length > 0 ? (
                <div className="space-y-3">
                  {runHistory.map(run => {
                    const isActive = activeRun?.taskId === run.taskId;
                    const isViewed = viewedLogId === run.taskId;
                    return (
                      <div
                        key={run.taskId}
                        className={`glass-card p-4 border transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-4 ${
                          isActive || isViewed ? 'border-primary/30 bg-primary/[0.02]' : 'border-slate-100 hover:bg-slate-50/50'
                        }`}
                      >
                        <div className="min-w-0 space-y-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-sm font-semibold text-slate-900">{run.engine}</span>
                            <span className={`inline-flex items-center gap-1.5 text-[10px] px-2.5 py-0.5 rounded-lg font-bold uppercase tracking-wider border ${runBadgeClass(run.status)}`}>
                              {run.status === 'running' && <StatusDot tone="running" pulse />}
                              {run.status}
                            </span>
                            {run.exitCode !== undefined && run.exitCode !== null && (
                              <span className="text-xs font-mono text-slate-500 bg-slate-100 px-1.5 py-0.5 rounded">
                                {t('taskDetail.exitCode')}: {run.exitCode}
                              </span>
                            )}
                          </div>
                          <p className="text-xs text-slate-400">
                            {new Date(run.startTime * 1000).toLocaleString()} · {t('taskDetail.duration')}: {formatDuration(runDuration(run))}
                          </p>
                        </div>

                        <div className="flex items-center gap-2 shrink-0">
                          <button
                            type="button"
                            onClick={() => {
                              setViewedLogId(run.taskId);
                              setActiveTab('logs');
                            }}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-colors bg-white border-slate-200 text-slate-600 hover:bg-slate-50 hover:text-primary"
                          >
                            <Terminal className="w-3.5 h-3.5" />
                            <span>{t('taskDetail.tabLogs')}</span>
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              setViewedLogId(run.taskId);
                              setActiveTab('changes');
                            }}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-colors bg-white border-slate-200 text-slate-600 hover:bg-slate-50 hover:text-primary"
                          >
                            <GitBranch className="w-3.5 h-3.5" />
                            <span>{t('taskDetail.tabChanges')}</span>
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="text-xs text-slate-400 italic p-12 bg-slate-50 rounded-xl border border-dashed border-slate-200 text-center">
                  {t('taskDetail.noRuns')}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Right: Inspector Panel (4 cols) */}
        <div className="lg:col-span-4 space-y-6">
          {/* 1. Recent Run Overview Card */}
          <section className="space-y-3">
            <h2 className="text-xs font-bold text-slate-400 uppercase tracking-widest flex items-center gap-2">
              <History className="w-3.5 h-3.5" />
              {t('taskDetail.runHistory')}
            </h2>

            {metaRun ? (
              <div className="glass-card p-4 border-slate-100 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-slate-700 truncate">
                    {lang === 'zh' ? '最新执行概览' : 'Latest Run Overview'}
                  </span>
                  <span className={`inline-flex items-center gap-1.5 text-[10px] px-2.5 py-0.5 rounded-lg font-bold uppercase tracking-wider border ${runBadgeClass(metaRun.status)}`}>
                    {metaRun.status === 'running' && <StatusDot tone="running" pulse />}
                    {metaRun.status}
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className="p-2.5 bg-slate-50/80 rounded-xl border border-slate-100">
                    <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block mb-0.5">{t('filters.engine')}</span>
                    <span className="font-semibold text-slate-800 truncate block">{metaRun.engine}</span>
                  </div>
                  <div className="p-2.5 bg-slate-50/80 rounded-xl border border-slate-100">
                    <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block mb-0.5">{t('taskDetail.duration')}</span>
                    <span className="font-semibold text-slate-800 block">{formatDuration(runDuration(metaRun))}</span>
                  </div>
                  {metaRun.exitCode !== undefined && metaRun.exitCode !== null && (
                    <div className="p-2.5 bg-slate-50/80 rounded-xl border border-slate-100 col-span-2">
                      <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block mb-0.5">{t('taskDetail.exitCode')}</span>
                      <span className="font-mono font-semibold text-slate-800">{metaRun.exitCode}</span>
                    </div>
                  )}
                </div>

                {runHistory.length > 0 && (
                  <div className="space-y-1.5 pt-2 border-t border-slate-100">
                    <div className="flex items-center justify-between text-[11px] text-slate-400">
                      <span>{t('taskDetail.runsCount', { count: runHistory.length })}</span>
                      <button
                        type="button"
                        onClick={() => setActiveTab('history')}
                        className="text-primary font-semibold hover:underline"
                      >
                        {t('taskDetail.tabHistory')} &rarr;
                      </button>
                    </div>
                    <div className="space-y-1 max-h-44 overflow-y-auto">
                      {runHistory.map(run => {
                        const isViewed = (logTaskId ?? metaRun?.taskId) === run.taskId;
                        return (
                          <button
                            key={run.taskId}
                            type="button"
                            onClick={() => {
                              setViewedLogId(run.taskId);
                              setActiveTab('logs');
                            }}
                            className={`w-full text-left p-2 rounded-lg border transition-all flex items-center justify-between gap-2 ${
                              isViewed ? 'border-primary/30 bg-primary/5' : 'border-slate-100 bg-slate-50/50 hover:bg-slate-100/60'
                            }`}
                          >
                            <div className="min-w-0">
                              <div className="flex items-center gap-1.5">
                                <span className="text-xs font-medium text-slate-800 truncate">{run.engine}</span>
                                <span className={`text-[9px] px-1.5 py-0.5 rounded font-bold uppercase tracking-wider border ${runBadgeClass(run.status)}`}>
                                  {run.status}
                                </span>
                              </div>
                              <p className="text-[10px] text-slate-400 mt-0.5">
                                {formatDuration(runDuration(run))}
                                {run.exitCode !== undefined && run.exitCode !== null && ` · ${t('taskDetail.exitCode')} ${run.exitCode}`}
                              </p>
                            </div>
                            {isViewed && <Terminal className="w-3 h-3 text-primary shrink-0" />}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-xs text-slate-400 italic p-4 bg-slate-50 rounded-xl border border-dashed border-slate-200">
                {t('taskDetail.noRuns')}
              </div>
            )}
          </section>

          {/* 2. Quick Schedule Automation Card */}
          <section className="glass-card p-5 border-slate-100 space-y-3 bg-gradient-to-br from-primary/[0.03] to-transparent">
            <div className="flex items-center gap-2 text-slate-800 font-semibold text-sm">
              <Clock className="w-4 h-4 text-primary" />
              <span>{t('taskDetail.scheduleThisTask')}</span>
            </div>
            <p className="text-xs text-slate-500 leading-relaxed">
              {lang === 'zh'
                ? '将此任务配置为定时自动化计划，按周期自动触发执行。'
                : 'Configure this task to run automatically on a recurring schedule.'}
            </p>
            <button
              type="button"
              onClick={goToSchedule}
              className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 rounded-xl text-xs font-semibold transition-colors shadow-sm"
            >
              <Clock className="w-3.5 h-3.5 text-primary" />
              <span>{lang === 'zh' ? '前往定时计划' : 'Go to Schedules'}</span>
            </button>
          </section>

          {/* 3. Mounted Skills */}
          <section className="space-y-3">
            <h2 className="text-xs font-bold text-slate-400 uppercase tracking-widest flex items-center gap-2">
              <Terminal className="w-3.5 h-3.5" />
              {t('taskDetail.mountedSkills')}
            </h2>
            <div className="space-y-2">
              {task.resolvedSkills && task.resolvedSkills.length > 0 ? (
                task.resolvedSkills.map(skill => (
                  <div key={skill.id} className="glass-card p-3.5 border-slate-100 space-y-1.5">
                    <div className="flex items-center gap-2">
                      <Code className="w-4 h-4 text-primary shrink-0" />
                      <span className="text-sm font-semibold text-slate-900 truncate">{skill.name}</span>
                    </div>
                    {skill.description && (
                      <p className="text-xs text-slate-500 line-clamp-2 leading-relaxed">{skill.description}</p>
                    )}
                    {skill.scripts && skill.scripts.length > 0 && (
                      <div className="pt-1 flex flex-wrap gap-1">
                        {skill.scripts.map(s => (
                          <span key={s} className="px-1.5 py-0.5 bg-slate-100 text-slate-600 rounded text-[10px] font-mono">
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

          {/* 4. Injected Prompts */}
          <section className="space-y-3">
            <h2 className="text-xs font-bold text-slate-400 uppercase tracking-widest flex items-center gap-2">
              <BookOpen className="w-3.5 h-3.5" />
              {t('taskDetail.injectedPrompts')}
            </h2>
            <div className="flex flex-wrap gap-1.5">
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
          description={
            linkedScheduleCount > 0
              ? `${t('taskDetail.confirmDeleteDescription', { name: task.title })}\n\n${t('taskDetail.deleteLinkedSchedules', { count: linkedScheduleCount })}`
              : t('taskDetail.confirmDeleteDescription', { name: task.title })
          }
          confirmLabel={t('common.delete')}
          onConfirm={() => void handleDelete()}
          onCancel={() => setConfirmDelete(false)}
        />
      )}
    </div>
  );
}
