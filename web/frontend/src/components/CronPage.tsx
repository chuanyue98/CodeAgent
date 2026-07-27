import { useCallback, useEffect, useMemo, useState } from 'react';
import { Clock, Plus, Trash2, Play, AlertCircle, PauseCircle, PlayCircle, Pencil, X } from 'lucide-react';
import cronstrue from 'cronstrue';
import { useProject } from '../context/ProjectContext';
import usePolling from '../hooks/usePolling';
import request from '../utils/request';
import ConfirmDialog from './shared/ConfirmDialog';
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
      request<{ valid: boolean; next_runs: number[] }>(
        `/api/schedules/preview?cron_expr=${encodeURIComponent(trimmed)}`,
      )
        .then(result => setCronPreview({ valid: result.valid, nextRuns: result.next_runs }))
        .catch(() => setCronPreview({ valid: false, nextRuns: [] }));
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
      .then(setSchedules)
      .catch(() => setError('Failed to load schedules'));
  }, []);

  useEffect(() => {
    request<Task[]>('/api/tasks')
      .then((list) => {
        setTasks(list);
        if (list.length > 0) setTaskName(prev => prev || list[0].name);
      })
      .catch(() => setError('Failed to load tasks'));

    request<Engine[]>('/api/engines')
      .then((list) => {
        setEngines(list);
        if (list.length > 0) setEngine(prev => prev || list[0].id);
      })
      .catch(() => setError('Failed to load engines'));
  }, []);

  usePolling(loadSchedules, POLL_INTERVAL_MS);

  const handleSave = async () => {
    if (!taskName || !engine || !workspace || !cronExpr.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const project = projects.find(item => item.path === workspace);
      const values = {
        task_name: taskName,
        engine,
        group: project?.group || 'common',
        workspace,
        cron_expr: cronExpr.trim(),
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
            ? 'Failed to update schedule'
            : 'Failed to create schedule',
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
    setTaskName(schedule.task_name);
    setEngine(schedule.engine);
    setCronExpr(schedule.cron_expr);
    setWorkspace(scheduleWorkspace || '');
    setError(null);
  };

  const toggleEnabled = async (schedule: Schedule) => {
    try {
      await updateSchedule(schedule.id, { enabled: !schedule.enabled });
      loadSchedules();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update schedule');
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
      setError(e instanceof Error ? e.message : 'Failed to delete schedule');
    }
  };

  const pendingDeleteSchedule = schedules.find(s => s.id === pendingDeleteId) || null;

  const handleRunNow = async (id: string) => {
    try {
      await runScheduleNow(id);
      loadSchedules();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to run schedule');
    }
  };

  return (
    <div className="flex flex-col lg:flex-row gap-4 min-h-full lg:h-full">
      <section className="w-full lg:w-80 shrink-0 glass-card p-5 space-y-4">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">
          <Clock className="w-4 h-4" /> {editingScheduleId ? 'Edit Schedule' : 'New Schedule'}
        </div>

        <div>
          <label className="text-xs text-slate-400 font-medium block mb-1">Workspace</label>
          <select
            aria-label="Workspace"
            value={workspace}
            onChange={e => setWorkspace(e.target.value)}
            className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg bg-white focus:outline-none focus:border-primary"
          >
            <option value="" disabled>Select workspace</option>
            {projects.filter(project => project.available !== false).map(project => (
              <option key={project.path} value={project.path}>{project.path}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="text-xs text-slate-400 font-medium block mb-1">Task</label>
          <select
            aria-label="Task"
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
          <label className="text-xs text-slate-400 font-medium block mb-1">Engine</label>
          <select
            aria-label="Engine"
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
            Cron expression
          </label>
          <input
            type="text"
            value={cronExpr}
            onChange={e => setCronExpr(e.target.value)}
            placeholder="0 9 * * *"
            className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg bg-white font-mono focus:outline-none focus:border-primary"
          />
          <p className="text-[10px] text-slate-400 mt-1">
            Standard 5-field cron syntax (minute hour day-of-month month day-of-week).
          </p>
          {cronExpr.trim() && (
            <div className="mt-1.5 rounded-lg border border-slate-100 bg-slate-50 px-2.5 py-2 text-xs">
              {cronPreview.valid ? (
                <>
                  <p className="font-medium text-slate-600">{cronDescription}</p>
                  {cronPreview.nextRuns.length > 0 && (
                    <p className="mt-1 text-[11px] text-slate-400">
                      Next: {formatTimestamp(cronPreview.nextRuns[0])}
                    </p>
                  )}
                </>
              ) : (
                <p className="text-red-500">Invalid cron expression — check the syntax above.</p>
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
          {editingScheduleId ? 'Save Schedule' : 'Create Schedule'}
        </button>
        {editingScheduleId && (
          <button
            onClick={() => setEditingScheduleId(null)}
            className="w-full flex items-center justify-center gap-2 px-3 py-2 border border-slate-200 text-slate-600 rounded-lg text-sm font-medium hover:bg-slate-50"
          >
            <X className="w-4 h-4" /> Cancel Editing
          </button>
        )}
      </section>

      <div className="flex-1 min-w-0 glass-card p-5 flex flex-col">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-700 mb-3">
          <Clock className="w-4 h-4" /> Schedules
        </div>

        {error && (
          <div className="mb-3 flex items-center gap-2 px-3 py-2 bg-red-50/60 border border-red-100 rounded-lg text-xs text-red-600">
            <AlertCircle className="w-3.5 h-3.5 shrink-0" /> {error}
          </div>
        )}

        <div className="flex-1 overflow-y-auto space-y-2">
          {schedules.length === 0 && (
            <p className="text-sm text-slate-500 text-center py-8">
              No schedules yet. Create one to run a task automatically.
            </p>
          )}
          {schedules.map(schedule => (
            <div
              key={schedule.id}
              className={`glass-card p-4 border-slate-100 flex flex-wrap items-center gap-3 ${
                !schedule.enabled ? 'opacity-50' : ''
              }`}
            >
              <button
                onClick={() => void toggleEnabled(schedule)}
                title={schedule.enabled ? 'Disable' : 'Enable'}
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
                    {schedule.task_name}
                  </span>
                  <span className="text-[10px] px-1.5 py-0.5 bg-slate-100 text-slate-500 rounded font-mono">
                    {schedule.engine}
                  </span>
                  <span className="text-[10px] px-1.5 py-0.5 bg-slate-100 text-slate-500 rounded font-mono">
                    {schedule.cron_expr}
                  </span>
                  <span className="text-[10px] px-1.5 py-0.5 bg-primary/5 text-primary rounded truncate max-w-56">
                    {schedule.workspace || 'Workspace required'}
                  </span>
                </div>
                <div className="text-xs text-slate-500 mt-0.5 flex flex-wrap items-center gap-3">
                  <span>Next: {formatTimestamp(schedule.next_run_at)}</span>
                  {schedule.last_run_status && (
                    <span>
                      Last: {schedule.last_run_status} ({formatTimestamp(schedule.last_run_at)})
                    </span>
                  )}
                </div>
              </div>

              <button
                onClick={() => handleEdit(schedule)}
                title="Edit"
                className="shrink-0 p-1.5 text-slate-400 hover:text-primary transition-colors"
              >
                <Pencil className="w-4 h-4" />
              </button>
              <button
                onClick={() => void handleRunNow(schedule.id)}
                title="Run now"
                className="shrink-0 p-1.5 text-slate-400 hover:text-primary transition-colors"
              >
                <Play className="w-4 h-4" />
              </button>
              <button
                onClick={() => setPendingDeleteId(schedule.id)}
                title="Delete"
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
          title="Delete this schedule?"
          description={`"${pendingDeleteSchedule.task_name}" (${pendingDeleteSchedule.cron_expr}) will stop running. This cannot be undone.`}
          confirmLabel="Delete"
          onConfirm={() => void confirmDelete()}
          onCancel={() => setPendingDeleteId(null)}
        />
      )}
    </div>
  );
}
