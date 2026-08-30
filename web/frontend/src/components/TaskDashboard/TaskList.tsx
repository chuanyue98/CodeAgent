import { memo, useMemo, useState } from 'react';
import { Activity, ChevronRight, FileText, Layers, Plus, Sparkles } from 'lucide-react';
import { useLanguageCode, useT } from '../../i18n/context';
import { relativeTime } from '../../utils/workspaceFormat';
import { formatDuration } from '../../utils/sessionProgress';
import Badge from '../shared/Badge';
import Button from '../shared/Button';
import EmptyState from '../shared/EmptyState';
import { SearchInput } from '../shared/Field';
import SectionLabel from '../shared/SectionLabel';
import StatusDot from '../shared/StatusDot';
import { classifyStageStatus, type RunStatus, type Stage, type Task } from './types';

function StageProgress({ stages }: { stages: Stage[] }) {
  const done = stages.filter(s => classifyStageStatus(s.status) === 'done').length;
  const pct = stages.length > 0 ? Math.round((done / stages.length) * 100) : 0;
  return (
    <div className="flex items-center gap-2 mt-2">
      <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div className="h-full bg-primary rounded-full transition-all duration-700" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[10px] text-slate-400 font-medium w-8 text-right">{pct}%</span>
    </div>
  );
}

function runTone(status: RunStatus['status']) {
  if (status === 'completed') return 'success' as const;
  if (status === 'failed') return 'failed' as const;
  if (status === 'stopped') return 'neutral' as const;
  return 'running' as const;
}

function runStartedAt(run: RunStatus): string {
  return new Date(run.startTime * 1000).toISOString();
}

/**
 * One task row. Memoized so the surrounding 5s list poll re-renders only the
 * cards whose task or running-state actually changed, not the whole grid.
 */
const TaskCard = memo(function TaskCard({
  task,
  activeRun,
  lastRun,
  onSelect,
}: {
  task: Task;
  activeRun: RunStatus | undefined;
  lastRun: RunStatus | undefined;
  onSelect: (name: string) => void;
}) {
  const t = useT();
  const language = useLanguageCode();
  return (
    <button
      onClick={() => onSelect(task.name)}
      className="glass-card glass-card-interactive p-5 text-left group flex items-start gap-4"
    >
      <div className="p-2.5 bg-slate-100 rounded-xl group-hover:bg-primary/10 transition-colors flex-shrink-0 mt-0.5">
        {task.hasStages
          ? <Layers className="w-5 h-5 text-slate-400 group-hover:text-primary transition-colors" />
          : <FileText className="w-5 h-5 text-slate-400 group-hover:text-primary transition-colors" />}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-3 min-w-0">
            <h2 className="font-semibold text-slate-900 truncate">{task.title}</h2>
            {activeRun && (
              <span className="flex items-center gap-1.5 px-2 py-0.5 bg-emerald-50 text-emerald-600 rounded-full text-[10px] font-bold uppercase tracking-wider border border-emerald-100">
                <StatusDot tone="running" pulse />
                {t('tasks.runningOn', { engine: activeRun.engine })}</span>
            )}
          </div>
          <ChevronRight className="w-4 h-4 text-slate-300 group-hover:text-primary flex-shrink-0 transition-colors" />
        </div>
        {task.description && (
          <p className="text-sm text-slate-500 mt-0.5 line-clamp-2">{task.description}</p>
        )}
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-400">
          {lastRun ? (
            <>
              <StatusDot tone={runTone(lastRun.status)} pulse={lastRun.status === 'running'} />
              <span>{t('tasks.lastRun', { time: relativeTime(runStartedAt(lastRun), language) })}</span>
              <Badge variant="engine" size="sm" engine={lastRun.engine}>{lastRun.engine}</Badge>
            </>
          ) : (
            <>
              <StatusDot tone="neutral" />
              <span>{t('tasks.neverRun')}</span>
            </>
          )}
        </div>
        {task.hasStages && <StageProgress stages={task.stages} />}
      </div>
    </button>
  );
});

function StatChip({ label, value, live }: { label: string; value: number; live?: boolean }) {
  return (
    <div className="rounded-lg bg-slate-50 px-2.5 py-1.5">
      <div className="flex items-center gap-1.5">
        {live && <StatusDot tone="running" pulse />}
        <span className="text-base font-semibold text-slate-800">{value}</span>
      </div>
      <p className="text-[10px] text-slate-400">{label}</p>
    </div>
  );
}

export default memo(function TaskList({
  tasks,
  runs,
  onSelect,
  onGenerateClick,
  onManualCreateClick,
}: {
  tasks: Task[];
  runs: RunStatus[];
  onSelect: (name: string) => void;
  onGenerateClick: () => void;
  onManualCreateClick: () => void;
}) {
  const t = useT();
  const language = useLanguageCode();
  const [search, setSearch] = useState('');

  const activeRunByTask = useMemo(() => {
    const map = new Map<string, RunStatus>();
    for (const run of runs) {
      if (run.status !== 'running') continue;
      const owner = tasks.find(task => run.taskId.startsWith(task.name));
      if (owner && !map.has(owner.name)) map.set(owner.name, run);
    }
    return map;
  }, [tasks, runs]);

  const lastRunByTask = useMemo(() => {
    const map = new Map<string, RunStatus>();
    for (const run of runs) {
      if (run.status === 'running') continue;
      const owner = tasks.find(task => run.taskId.startsWith(task.name));
      if (!owner) continue;
      const current = map.get(owner.name);
      if (!current || run.startTime > current.startTime) map.set(owner.name, run);
    }
    return map;
  }, [tasks, runs]);

  // Active work first, then whatever ran most recently, then alphabetical —
  // the dashboard reads top-down in order of "what deserves attention".
  const sortedTasks = useMemo(() => {
    return [...tasks].sort((a, b) => {
      const aActive = activeRunByTask.has(a.name) ? 1 : 0;
      const bActive = activeRunByTask.has(b.name) ? 1 : 0;
      if (aActive !== bActive) return bActive - aActive;
      const aTime = lastRunByTask.get(a.name)?.startTime ?? 0;
      const bTime = lastRunByTask.get(b.name)?.startTime ?? 0;
      if (aTime !== bTime) return bTime - aTime;
      return a.title.localeCompare(b.title);
    });
  }, [tasks, activeRunByTask, lastRunByTask]);

  const filteredTasks = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return sortedTasks;
    return sortedTasks.filter(task =>
      task.name.toLowerCase().includes(q) ||
      task.title.toLowerCase().includes(q) ||
      task.description.toLowerCase().includes(q),
    );
  }, [sortedTasks, search]);

  const runStats = useMemo(() => ({
    running: runs.filter(r => r.status === 'running').length,
    completed: runs.filter(r => r.status === 'completed').length,
    failed: runs.filter(r => r.status === 'failed').length,
  }), [runs]);

  const recentRuns = useMemo(
    () => [...runs].sort((a, b) => b.startTime - a.startTime).slice(0, 30),
    [runs],
  );

  // taskId is `${taskName}-<timestamp>`-ish; taskName is authoritative when
  // the runner sent it, the prefix match covers history rows that predate it.
  const resolveTask = (run: RunStatus) =>
    tasks.find(task => (run.taskName && run.taskName === task.name) || run.taskId.startsWith(task.name));

  return (
    <div className="flex flex-col xl:flex-row gap-4 min-h-full xl:h-full">
      <section
        className={`flex-1 min-w-0 flex flex-col min-h-0 ${
          tasks.length === 0 ? '' : 'glass-card p-4 sm:p-6'
        }`}
      >
        {/* The app shell already renders "Tasks" as the page's <h1>, so a second
            oversized title here just pushed the actual content below the fold. */}
        <div className="flex flex-wrap justify-between items-center gap-3 pb-4">
          <div className="min-w-0">
            <p className="text-sm text-slate-500">
              {tasks.length === 1
              ? t('tasks.countOne', { count: tasks.length })
              : t('tasks.count', { count: tasks.length })}
            </p>
          </div>
          {/* Hidden while the list is empty: the empty state below carries its
              own (better-labeled) create buttons, and showing both pairs at
              once duplicated the same two actions on one screen. */}
          {tasks.length > 0 && (
            <div className="flex items-center gap-2">
              <Button variant="outline" icon={Plus} onClick={onManualCreateClick} title={t('tasks.manualTitle')}>
                {t('tasks.manual')}
              </Button>
              <Button icon={Sparkles} onClick={onGenerateClick}>
                {t('tasks.generate')}
              </Button>
            </div>
          )}
        </div>

        {tasks.length > 5 && (
          <div className="max-w-sm pb-4">
            <label htmlFor="task-search" className="sr-only">{t('tasks.searchLabel')}</label>
            <SearchInput
              id="task-search"
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder={t('tasks.searchPlaceholder')}
            />
          </div>
        )}

        {tasks.length === 0 && (
          <EmptyState
            className="flex-1"
            icon={Activity}
            title={t('tasks.emptyTitle')}
            body={t('tasks.emptyBody')}
            action={
              <>
                <Button icon={Sparkles} onClick={onGenerateClick}>{t('tasks.describeIt')}</Button>
                <Button variant="outline" icon={Plus} onClick={onManualCreateClick}>
                  {t('tasks.writeItMyself')}
                </Button>
              </>
            }
          />
        )}

        {tasks.length > 0 && (
          <div className="custom-scrollbar flex-1 min-h-0 overflow-y-auto space-y-3 pr-1">
            {tasks.length > 5 && filteredTasks.length === 0 && (
              <EmptyState compact title={t('tasks.noSearchMatch')} />
            )}
            {filteredTasks.map(task => (
              <TaskCard
                key={task.name}
                task={task}
                activeRun={activeRunByTask.get(task.name)}
                lastRun={lastRunByTask.get(task.name)}
                onSelect={onSelect}
              />
            ))}
          </div>
        )}
      </section>

      {tasks.length > 0 && (
        <aside
          aria-label={t('tasks.activityTitle')}
          className="w-full xl:w-80 shrink-0 glass-card flex flex-col p-5 gap-3 min-h-0"
        >
          <div className="flex items-center justify-between gap-2">
            <SectionLabel>{t('tasks.activityTitle')}</SectionLabel>
            <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-semibold text-primary">
              {runs.length}
            </span>
          </div>

          <div className="grid grid-cols-3 gap-2">
            <StatChip label={t('tasks.statRunning')} value={runStats.running} live={runStats.running > 0} />
            <StatChip label={t('tasks.statCompleted')} value={runStats.completed} />
            <StatChip label={t('tasks.statFailed')} value={runStats.failed} />
          </div>

          <div className="custom-scrollbar flex-1 min-h-0 overflow-y-auto space-y-1">
            {recentRuns.map(run => {
              const owner = resolveTask(run);
              const duration = run.endTime
                ? formatDuration((run.endTime - run.startTime) * 1000)
                : null;
              return (
                <button
                  key={run.taskId}
                  onClick={() => onSelect(owner?.name ?? run.taskName ?? run.taskId)}
                  className="w-full text-left rounded-xl px-3 py-2.5 hover:bg-slate-50 transition-colors"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <StatusDot tone={runTone(run.status)} pulse={run.status === 'running'} />
                    <span className="flex-1 min-w-0 truncate text-sm font-medium text-slate-700">
                      {owner?.title ?? run.taskName ?? run.taskId}
                    </span>
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-2 pl-4 text-[10px] text-slate-400">
                    <Badge variant="engine" size="sm" engine={run.engine}>{run.engine}</Badge>
                    <span>{relativeTime(runStartedAt(run), language)}</span>
                    {duration && <span>· {duration}</span>}
                  </div>
                </button>
              );
            })}
            {recentRuns.length === 0 && (
              <EmptyState compact title={t('tasks.runFeedEmpty')} />
            )}
          </div>
        </aside>
      )}
    </div>
  );
});
