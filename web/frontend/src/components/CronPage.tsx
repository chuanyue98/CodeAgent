import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Clock, Plus, Trash2, Play, PauseCircle, PlayCircle, Pencil, X, Search, Sparkles, CheckCircle2 } from 'lucide-react';
import cronstrue from 'cronstrue';
import { useProject } from '../context/ProjectContext';
import { useT } from '../i18n/context';
import usePolling from '../hooks/usePolling';
import request from '../utils/request';
import ConfirmDialog from './shared/ConfirmDialog';
import ErrorState from './shared/ErrorState';
import TaskTemplateGallery from './cron/TaskTemplateGallery';
import type { TaskTemplate } from '../data/taskTemplates';
import {
  fetchSchedules,
  createSchedule,
  updateSchedule,
  deleteSchedule,
  runScheduleNow,
  type Schedule,
} from '../api/schedules';

interface Task {
  name: string;
  title: string;
}

interface Engine {
  id: string;
  name: string;
}

const POLL_INTERVAL_MS = 10000;

/** Task blueprint payload accepted by POST /api/tasks. */
interface TaskBlueprint {
  name: string;
  title: string;
  objective: string;
  context: string;
  instructions: string;
  verification: string;
}

function formatTimestamp(ts: number | null): string {
  if (ts === null) return '—';
  return new Date(ts * 1000).toLocaleString();
}

export default function CronPage() {
  const {
    projects,
    selectedWorkspace: workspace,
    setSelectedWorkspace: setWorkspace,
  } = useProject();
  const t = useT();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [engines, setEngines] = useState<Engine[]>([]);
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [taskName, setTaskName] = useState('');
  const [engine, setEngine] = useState('');
  const [cronExpr, setCronExpr] = useState('0 9 * * *');
  const [editingScheduleId, setEditingScheduleId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [cronPreview, setCronPreview] = useState<{ valid: boolean; nextRuns: number[] }>({
    valid: true,
    nextRuns: [],
  });
  const [scheduleSearch, setScheduleSearch] = useState('');
  const [templateBusyId, setTemplateBusyId] = useState<string | null>(null);
  const [templateNotice, setTemplateNotice] = useState<string | null>(null);
  const [showTemplates, setShowTemplates] = useState(false);

  // Guards setState calls in async fetches below from firing after the
  // component has unmounted (e.g. a fast workspace/page switch while a
  // request is still in flight).
  const mountedRef = useRef(true);
  useEffect(() => {
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // Debounced live preview: translates the raw cron syntax into plain
  // English and the next few actual fire times, so the user isn't expected
  // to already know cron syntax to tell whether what they typed is right.
  // The validity/next-run computation is authoritative from the backend
  // (same croniter call the schedule itself will use) -- cronstrue only
  // supplies the English description, so the two can never contradict on
  // whether the expression is valid.
  useEffect(() => {
    const trimmed = cronExpr.trim();
    if (!trimmed) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setCronPreview({ valid: true, nextRuns: [] });
      return;
    }
    const handle = window.setTimeout(() => {
      request<{ valid: boolean; nextRuns: number[] }>(
        `/api/schedules/preview?cron_expr=${encodeURIComponent(trimmed)}`,
      )
        .then(result => {
          if (!mountedRef.current) return;
          setCronPreview({ valid: result.valid, nextRuns: result.nextRuns });
        })
        .catch(() => {
          if (!mountedRef.current) return;
          setCronPreview({ valid: false, nextRuns: [] });
        });
    }, 300);
    return () => window.clearTimeout(handle);
  }, [cronExpr]);

  const cronDescription = useMemo(() => {
    const trimmed = cronExpr.trim();
    if (!trimmed || !cronPreview.valid) return '';
    return cronstrue.toString(trimmed, { throwExceptionOnParseError: false });
  }, [cronExpr, cronPreview.valid]);

  const loadSchedules = useCallback(() => {
    fetchSchedules()
      .then(list => {
        if (!mountedRef.current) return;
        setSchedules(list);
      })
      .catch(() => {
        if (!mountedRef.current) return;
        setError(t('cron.loadSchedulesFailed'));
      });
  }, [t]);

  const retrySchedules = useCallback(() => {
    setError(null);
    loadSchedules();
  }, [loadSchedules]);

  const loadTasks = useCallback(async (): Promise<Task[]> => {
    const list = await request<Task[]>('/api/tasks');
    if (mountedRef.current) {
      setTasks(list);
      if (list.length > 0) setTaskName(prev => prev || list[0].name);
    }
    return list;
  }, []);

  useEffect(() => {
    // loadTasks only touches state after its await, but the rule cannot see
    // past the call, so the same disable the other pages use applies here.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadTasks().catch(() => {
      if (!mountedRef.current) return;
      setError(t('cron.loadTasksFailed'));
    });

    request<Engine[]>('/api/engines')
      .then((list) => {
        if (!mountedRef.current) return;
        setEngines(list);
        if (list.length > 0) setEngine(prev => prev || list[0].id);
      })
      .catch(() => {
        if (!mountedRef.current) return;
        setError(t('cron.loadEnginesFailed'));
      });
  }, [loadTasks, t]);

  usePolling(loadSchedules, POLL_INTERVAL_MS);

  /**
   * Writes the template's blueprint to tasks/<id>.md and prefills the form
   * with it. Deliberately stops there: creating the schedule too would put a
   * recurring job on the user's machine from a single click on a card.
   */
  const handleUseTemplate = async (template: TaskTemplate) => {
    setTemplateBusyId(template.id);
    setTemplateNotice(null);
    setError(null);

    const select = (existed: boolean) => {
      setTaskName(template.id);
      setCronExpr(template.cronExpr);
      setEditingScheduleId(null);
      setTemplateNotice(
        t(existed ? 'template.existed' : 'template.created', { name: t(template.titleKey) }),
      );
    };

    try {
      if (tasks.some(task => task.name === template.id)) {
        select(true);
        return;
      }
      const body: TaskBlueprint = {
        name: template.id,
        title: t(template.titleKey),
        objective: t(template.objectiveKey),
        context: t(template.contextKey),
        instructions: t(template.instructionsKey),
        verification: t(template.verificationKey),
      };
      try {
        await request('/api/tasks', { method: 'POST', body: JSON.stringify(body) });
        await loadTasks();
        select(false);
      } catch (createError) {
        // The list this component holds can be stale -- another tab, the CLI,
        // or an earlier click may have written the file already. Re-read
        // before believing the failure, so a lost race reads as "it's already
        // there" rather than an error.
        const fresh = await loadTasks().catch(() => [] as Task[]);
        if (fresh.some(task => task.name === template.id)) select(true);
        else throw createError;
      }
    } catch (e) {
      if (!mountedRef.current) return;
      setError(e instanceof Error ? e.message : t('template.createFailed'));
    } finally {
      if (mountedRef.current) setTemplateBusyId(null);
    }
  };

  const handleSave = async () => {
    if (!taskName || !engine || !workspace || !cronExpr.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const project = projects.find(item => item.path === workspace);
      const values = {
        taskName: taskName,
        engine,
        group: project?.group || 'common',
        workspace,
        cronExpr: cronExpr.trim(),
      };
      if (editingScheduleId) {
        await updateSchedule(editingScheduleId, values);
      } else {
        await createSchedule(values);
      }
      setEditingScheduleId(null);
      loadSchedules();
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : editingScheduleId
            ? t('cron.updateFailed')
            : t('cron.createFailed'),
      );
    } finally {
      setSubmitting(false);
    }
  };

  const handleEdit = (schedule: Schedule) => {
    const availableWorkspaces = projects.filter(project => project.available !== false);
    const scheduleWorkspace = availableWorkspaces.some(
      project => project.path === schedule.workspace,
    ) ? schedule.workspace : availableWorkspaces[0]?.path;
    setEditingScheduleId(schedule.id);
    setTaskName(schedule.taskName);
    setEngine(schedule.engine);
    setCronExpr(schedule.cronExpr);
    setWorkspace(scheduleWorkspace || '');
    setError(null);
  };

  const toggleEnabled = async (schedule: Schedule) => {
    try {
      await updateSchedule(schedule.id, { enabled: !schedule.enabled });
      loadSchedules();
    } catch (e) {
      setError(e instanceof Error ? e.message : t('cron.updateFailed'));
    }
  };

  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);

  const confirmDelete = async () => {
    const id = pendingDeleteId;
    if (!id) return;
    setPendingDeleteId(null);
    try {
      await deleteSchedule(id);
      if (editingScheduleId === id) setEditingScheduleId(null);
      loadSchedules();
    } catch (e) {
      setError(e instanceof Error ? e.message : t('cron.deleteFailed'));
    }
  };

  const pendingDeleteSchedule = schedules.find(s => s.id === pendingDeleteId) || null;

  const filteredSchedules = useMemo(() => {
    const q = scheduleSearch.trim().toLowerCase();
    if (!q) return schedules;
    return schedules.filter(schedule =>
      schedule.taskName.toLowerCase().includes(q) ||
      schedule.engine.toLowerCase().includes(q) ||
      schedule.cronExpr.toLowerCase().includes(q) ||
      (schedule.workspace || '').toLowerCase().includes(q),
    );
  }, [schedules, scheduleSearch]);

  const handleRunNow = async (id: string) => {
    try {
      await runScheduleNow(id);
      loadSchedules();
    } catch (e) {
      setError(e instanceof Error ? e.message : t('cron.runFailed'));
    }
  };

  return (
    <div className="flex flex-col lg:flex-row gap-4 min-h-full lg:h-full">
      <section className="w-full lg:w-80 shrink-0 glass-card p-5 space-y-4">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">
          <Clock className="w-4 h-4" /> {editingScheduleId ? t('cron.editTitle') : t('cron.newTitle')}
        </div>

        <div>
          <label className="text-xs text-slate-400 font-medium block mb-1">{t('filters.workspace')}</label>
          <select
            aria-label={t('filters.workspace')}
            value={workspace}
            onChange={e => setWorkspace(e.target.value)}
            className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg bg-white focus:outline-none focus:border-primary"
          >
            <option value="" disabled>{t('cron.selectWorkspace')}</option>
            {projects.filter(project => project.available !== false).map(project => (
              <option key={project.path} value={project.path}>{project.path}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="text-xs text-slate-400 font-medium block mb-1">{t('cron.task')}</label>
          <select
            aria-label={t('cron.task')}
            value={taskName}
            onChange={e => setTaskName(e.target.value)}
            className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg bg-white focus:outline-none focus:border-primary"
          >
            {tasks.map(t => (
              <option key={t.name} value={t.name}>
                {t.title || t.name}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="text-xs text-slate-400 font-medium block mb-1">{t('filters.engine')}</label>
          <select
            aria-label={t('filters.engine')}
            value={engine}
            onChange={e => setEngine(e.target.value)}
            className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg bg-white focus:outline-none focus:border-primary"
          >
            {engines.map(e => (
              <option key={e.id} value={e.id}>
                {e.name}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="text-xs text-slate-400 font-medium block mb-1">
            {t('cron.expression')}
          </label>
          <input
            type="text"
            value={cronExpr}
            onChange={e => setCronExpr(e.target.value)}
            placeholder="0 9 * * *"
            className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg bg-white font-mono focus:outline-none focus:border-primary"
          />
          <p className="text-[10px] text-slate-400 mt-1">
            {t('cron.syntaxHint')}
          </p>
          {cronExpr.trim() && (
            <div className="mt-1.5 rounded-lg border border-slate-100 bg-slate-50 px-2.5 py-2 text-xs">
              {cronPreview.valid ? (
                <>
                  <p className="font-medium text-slate-600">{cronDescription}</p>
                  {cronPreview.nextRuns.length > 0 && (
                    <p className="mt-1 text-[11px] text-slate-400">
                      {t('cron.next', { time: formatTimestamp(cronPreview.nextRuns[0]) })}
                    </p>
                  )}
                </>
              ) : (
                <p className="text-red-500">{t('cron.invalid')}</p>
              )}
            </div>
          )}
        </div>

        <button
          onClick={() => void handleSave()}
          disabled={submitting || !taskName || !engine || !workspace || !cronExpr.trim()}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-primary text-white rounded-lg text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed hover:scale-[1.02] active:scale-95 transition-all"
        >
          {editingScheduleId ? <Pencil className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
          {editingScheduleId ? t('cron.save') : t('cron.create')}
        </button>
        {editingScheduleId && (
          <button
            onClick={() => setEditingScheduleId(null)}
            className="w-full flex items-center justify-center gap-2 px-3 py-2 border border-slate-200 text-slate-600 rounded-lg text-sm font-medium hover:bg-slate-50"
          >
            <X className="w-4 h-4" /> {t('cron.cancelEditing')}
          </button>
        )}
      </section>

      <div className="flex-1 min-w-0 glass-card p-5 flex flex-col">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">
            <Clock className="w-4 h-4" /> {t('cron.listTitle')}
            <span className="text-xs font-normal text-slate-400">
              ({filteredSchedules.length}{scheduleSearch ? ` / ${schedules.length}` : ''})
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
          {schedules.length > 0 && (
            <button
              onClick={() => setShowTemplates(value => !value)}
              aria-expanded={showTemplates}
              className="flex items-center gap-1 rounded-md border border-slate-200 px-2 py-1.5 text-xs font-medium text-slate-600 transition-colors hover:bg-slate-50"
            >
              <Sparkles className="h-3.5 w-3.5" />
              {showTemplates ? t('template.hide') : t('template.show')}
            </button>
          )}
          {schedules.length > 0 && (
            <div className="relative w-full max-w-56">
              <label htmlFor="schedule-search" className="sr-only">{t('cron.searchLabel')}</label>
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
              <input
                id="schedule-search"
                type="text"
                value={scheduleSearch}
                onChange={e => setScheduleSearch(e.target.value)}
                placeholder={t('cron.searchPlaceholder')}
                className="w-full pl-8 pr-3 py-1.5 text-xs border border-slate-200 rounded-lg bg-white focus:outline-none focus:border-primary"
              />
            </div>
          )}
          </div>
        </div>

        {error && (
          <div className="mb-3">
            <ErrorState message={error} onRetry={retrySchedules} />
          </div>
        )}

        {templateNotice && (
          <div className="mb-3 flex items-start gap-2 rounded-lg border border-emerald-100 bg-emerald-50/60 px-3 py-2 text-xs text-emerald-700">
            <CheckCircle2 className="mt-px h-3.5 w-3.5 shrink-0" />
            <span className="flex-1">{templateNotice}</span>
            <button
              onClick={() => setTemplateNotice(null)}
              aria-label={t('common.close')}
              className="shrink-0 text-emerald-500 transition-colors hover:text-emerald-700"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        )}

        <div className="flex-1 overflow-y-auto space-y-2">
          {schedules.length === 0 && (
            <div className="space-y-5 py-2">
              <p className="text-sm text-slate-500">{t('cron.empty')}</p>
              <TaskTemplateGallery busyId={templateBusyId} onUse={handleUseTemplate} />
            </div>
          )}
          {schedules.length > 0 && showTemplates && (
            <div className="mb-4 border-b border-slate-100 pb-4">
              <TaskTemplateGallery busyId={templateBusyId} onUse={handleUseTemplate} />
            </div>
          )}
          {schedules.length > 0 && filteredSchedules.length === 0 && (
            <p className="text-sm text-slate-400 text-center py-8">{t('cron.noSearchMatch')}</p>
          )}
          {filteredSchedules.map(schedule => (
            <div
              key={schedule.id}
              className={`glass-card p-4 border-slate-100 flex flex-wrap items-center gap-3 ${
                !schedule.enabled ? 'opacity-50' : ''
              }`}
            >
              <button
                onClick={() => void toggleEnabled(schedule)}
                title={schedule.enabled ? t('cron.disable') : t('cron.enable')}
                className="shrink-0 text-slate-400 hover:text-primary transition-colors"
              >
                {schedule.enabled ? (
                  <PlayCircle className="w-5 h-5" />
                ) : (
                  <PauseCircle className="w-5 h-5" />
                )}
              </button>

              <div className="flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-sm text-slate-800 truncate">
                    {schedule.taskName}
                  </span>
                  <span className="text-[10px] px-1.5 py-0.5 bg-slate-100 text-slate-500 rounded font-mono">
                    {schedule.engine}
                  </span>
                  <span className="text-[10px] px-1.5 py-0.5 bg-slate-100 text-slate-500 rounded font-mono">
                    {schedule.cronExpr}
                  </span>
                  <span className="text-[10px] px-1.5 py-0.5 bg-primary/5 text-primary rounded truncate max-w-56">
                    {schedule.workspace || t('cron.workspaceRequired')}
                  </span>
                </div>
                <div className="text-xs text-slate-500 mt-0.5 flex flex-wrap items-center gap-3">
                  <span>{t('cron.next', { time: formatTimestamp(schedule.nextRunAt) })}</span>
                  {schedule.lastRunStatus && (
                    <span>
                      {t('cron.last', { status: schedule.lastRunStatus, time: formatTimestamp(schedule.lastRunAt) })}
                    </span>
                  )}
                </div>
              </div>

              <button
                onClick={() => handleEdit(schedule)}
                title={t('common.edit')}
                className="shrink-0 p-1.5 text-slate-400 hover:text-primary transition-colors"
              >
                <Pencil className="w-4 h-4" />
              </button>
              <button
                onClick={() => void handleRunNow(schedule.id)}
                title={t('cron.runNow')}
                className="shrink-0 p-1.5 text-slate-400 hover:text-primary transition-colors"
              >
                <Play className="w-4 h-4" />
              </button>
              <button
                onClick={() => setPendingDeleteId(schedule.id)}
                title={t('common.delete')}
                className="shrink-0 p-1.5 text-slate-400 hover:text-red-500 transition-colors"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      </div>

      {pendingDeleteSchedule && (
        <ConfirmDialog
          title={t('cron.confirmDeleteTitle')}
          description={t('cron.confirmDeleteDescription', {
            task: pendingDeleteSchedule.taskName,
            expr: pendingDeleteSchedule.cronExpr,
          })}
          confirmLabel={t('common.delete')}
          onConfirm={() => void confirmDelete()}
          onCancel={() => setPendingDeleteId(null)}
        />
      )}
    </div>
  );
}
