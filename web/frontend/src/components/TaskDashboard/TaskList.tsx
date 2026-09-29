import { memo, useMemo, useState } from 'react';
import cronstrue from 'cronstrue/i18n';
import { Activity, Layers, Plus, Sparkles } from 'lucide-react';
import type { Schedule } from '../../api/schedules';
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
    <div className="mt-1.5 flex items-center gap-2">
      <div className="h-1 max-w-[12rem] flex-1 overflow-hidden rounded-full bg-muted">
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

/** "Every day at 09:00" for a cron expression; the raw expression when it does not parse. */
function describeCron(expr: string, language: string): string {
  try {
    return cronstrue.toString(expr, { locale: language === 'zh' ? 'zh_CN' : 'en', use24HourTimeFormat: true });
  } catch {
    return expr;
  }
}

const RUN_LABEL_KEY = {
  running: 'tasks.statRunning',
  completed: 'tasks.statCompleted',
  failed: 'tasks.statFailed',
  stopped: 'tasks.neverRun',
} as const;

const RUN_PILL: Record<RunStatus['status'], string> = {
  running: 'bg-primary/15 text-primary',
  completed: 'bg-ok/15 text-ok',
  failed: 'bg-destructive/15 text-destructive',
  stopped: 'bg-muted text-muted-foreground',
};

/**
 * One task as one row: what it is, when it fires, and how it last went.
 * Memoized so the surrounding 5s list poll re-renders only the rows whose task
 * or running-state actually changed.
 */
const TaskRow = memo(function TaskRow({
  task,
  activeRun,
  lastRun,
  schedule,
  onSelect,
}: {
  task: Task;
  activeRun: RunStatus | undefined;
  lastRun: RunStatus | undefined;
  schedule: Schedule | undefined;
  onSelect: (name: string) => void;
}) {
  const t = useT();
  const language = useLanguageCode();
  const shown = activeRun ?? lastRun;
  const lastRunDuration = lastRun?.endTime
    ? formatDuration((lastRun.endTime - lastRun.startTime) * 1000)
    : null;
  const nextRun = schedule?.enabled && schedule.nextRunAt
    ? relativeTime(new Date(schedule.nextRunAt * 1000).toISOString(), language)
    : null;

  return (
    <button
      type="button"
      onClick={() => onSelect(task.name)}
      className="grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-x-6 gap-y-1 px-4 py-3 text-left transition-colors hover:bg-muted/60 md:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)_minmax(0,0.8fr)_auto]"
    >
      <span className="min-w-0">
        <span className="flex items-center gap-2">
          <h2 className="truncate text-sm font-medium">{task.title}</h2>
          {task.hasStages && (
            <span className="inline-flex shrink-0 items-center gap-1 rounded bg-muted px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">
              <Layers className="h-2.5 w-2.5" />
              {task.stages.length > 0 ? `${task.stages.length} ${t('taskDetail.stages')}` : t('taskDetail.stages')}
            </span>
          )}
        </span>
        {task.description && <span className="mt-0.5 block truncate text-xs text-muted-foreground">{task.description}</span>}
        {task.hasStages && <StageProgress stages={task.stages} />}
      </span>

      <span className="hidden min-w-0 md:block">
        {schedule ? (
          <>
            <span className="block truncate text-xs text-foreground/80">{describeCron(schedule.cronExpr, language)}</span>
            <span className="block truncate text-xs text-muted-foreground">
              {nextRun ? t('tasks.nextRun', { time: nextRun }) : ''}
            </span>
          </>
        ) : (
          <span className="text-xs text-muted-foreground">{t('tasks.manualOnly')}</span>
        )}
      </span>

      <span className="hidden min-w-0 items-center gap-2 md:flex">
        {shown ? (
          <Badge variant="engine" size="sm" engine={shown.engine}>{shown.engine}</Badge>
        ) : null}
      </span>

      <span className="flex flex-col items-end gap-1">
        {shown ? (
          <>
            <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ${RUN_PILL[shown.status]}`}>
              {shown.status === 'running' && <StatusDot tone="running" pulse />}
              {t(RUN_LABEL_KEY[shown.status])}
            </span>
            <span className="text-xs text-muted-foreground">
              {activeRun
                ? t('tasks.runningOn', { engine: activeRun.engine })
                : `${relativeTime(runStartedAt(shown), language)}${lastRunDuration ? ` · ${lastRunDuration}` : ''}`}
            </span>
          </>
        ) : (
          <span className="text-xs text-muted-foreground">{t('tasks.neverRun')}</span>
        )}
      </span>
    </button>
  );
});

function StatChip({ label, value, live }: { label: string; value: number; live?: boolean }) {
  return (
    <div className="bg-card px-3 py-2.5">
      <div className="flex items-center gap-1.5">
        {live && <StatusDot tone="running" pulse />}
        <span className="font-mono text-lg font-medium tracking-tight">{value}</span>
      </div>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  );
}

export default memo(function TaskList({
  tasks,
  runs,
  onSelect,
  schedules = [],
  onGenerateClick,
  onManualCreateClick,
}: {
  tasks: Task[];
  runs: RunStatus[];
  /** Schedules whose task name matches a row show their cron and next run inline. */
  schedules?: Schedule[];
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

  const scheduleByTask = useMemo(() => {
    const map = new Map<string, Schedule>();
    for (const schedule of schedules) {
      // A task can have several schedules; the enabled one that fires soonest is the one to show.
      const current = map.get(schedule.taskName);
      const better = !current
        || (schedule.enabled && !current.enabled)
        || (schedule.enabled === current.enabled && (schedule.nextRunAt ?? Infinity) < (current.nextRunAt ?? Infinity));
      if (better) map.set(schedule.taskName, schedule);
    }
    return map;
  }, [schedules]);

  return (
    <div className="flex min-h-full flex-col gap-6 xl:h-full xl:flex-row">
      <section className="flex min-h-0 min-w-0 flex-1 flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-muted-foreground">
            {tasks.length === 1
              ? t('tasks.countOne', { count: tasks.length })
              : t('tasks.count', { count: tasks.length })}
          </p>
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
          <div className="max-w-sm">
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
          <div className="glass-card custom-scrollbar min-h-0 flex-1 divide-y divide-border overflow-y-auto">
            {tasks.length > 5 && filteredTasks.length === 0 && (
              <EmptyState compact title={t('tasks.noSearchMatch')} />
            )}
            {filteredTasks.map(task => (
              <TaskRow
                key={task.name}
                task={task}
                activeRun={activeRunByTask.get(task.name)}
                lastRun={lastRunByTask.get(task.name)}
                schedule={scheduleByTask.get(task.name)}
                onSelect={onSelect}
              />
            ))}
          </div>
        )}
      </section>

      {tasks.length > 0 && (
        <aside
          aria-label={t('tasks.activityTitle')}
          className="flex min-h-0 w-full shrink-0 flex-col gap-3 xl:w-80"
        >
          <div className="flex items-center justify-between gap-2">
            <SectionLabel>{t('tasks.activityTitle')}</SectionLabel>
            <span className="rounded-full bg-muted px-2 py-0.5 font-mono text-[11px] text-muted-foreground">
              {runs.length}
            </span>
          </div>

          <div className="grid grid-cols-3 gap-px overflow-hidden rounded-xl border border-border bg-border">
            <StatChip label={t('tasks.statRunning')} value={runStats.running} live={runStats.running > 0} />
            <StatChip label={t('tasks.statCompleted')} value={runStats.completed} />
            <StatChip label={t('tasks.statFailed')} value={runStats.failed} />
          </div>

          <div className="glass-card custom-scrollbar min-h-0 flex-1 divide-y divide-border overflow-y-auto">
            {recentRuns.map(run => {
              const owner = resolveTask(run);
              const duration = run.endTime
                ? formatDuration((run.endTime - run.startTime) * 1000)
                : null;
              return (
                <button
                  key={run.taskId}
                  onClick={() => onSelect(owner?.name ?? run.taskName ?? run.taskId)}
                  className="grid w-full grid-cols-[8px_minmax(0,1fr)] items-center gap-x-3 px-4 py-2.5 text-left transition-colors hover:bg-muted/60"
                >
                  <StatusDot tone={runTone(run.status)} pulse={run.status === 'running'} />
                  <span className="min-w-0 truncate text-sm font-medium">
                    {owner?.title ?? run.taskName ?? run.taskId}
                  </span>
                  <span />
                  <span className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <Badge variant="engine" size="sm" engine={run.engine}>{run.engine}</Badge>
                    <span>{relativeTime(runStartedAt(run), language)}</span>
                    {duration && <span>· {duration}</span>}
                  </span>
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
