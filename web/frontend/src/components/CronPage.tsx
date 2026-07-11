import { useCallback, useEffect, useState } from 'react';
import { Clock, Plus, Trash2, Play, AlertCircle, PauseCircle, PlayCircle } from 'lucide-react';
import { useProject } from '../context/ProjectContext';
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
  const { currentGroup } = useProject();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [engines, setEngines] = useState<Engine[]>([]);
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [taskName, setTaskName] = useState('');
  const [engine, setEngine] = useState('');
  const [cronExpr, setCronExpr] = useState('0 9 * * *');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const loadSchedules = useCallback(() => {
    fetchSchedules()
      .then(setSchedules)
      .catch(() => setError('Failed to load schedules'));
  }, []);

  useEffect(() => {
    fetch('/api/tasks')
      .then(res => res.json())
      .then((list: Task[]) => {
        setTasks(list);
        if (list.length > 0) setTaskName(prev => prev || list[0].name);
      })
      .catch(() => setError('Failed to load tasks'));

    fetch('/api/engines')
      .then(res => res.json())
      .then((list: Engine[]) => {
        setEngines(list);
        if (list.length > 0) setEngine(prev => prev || list[0].id);
      })
      .catch(() => setError('Failed to load engines'));

    loadSchedules();
  }, [loadSchedules]);

  useEffect(() => {
    const id = setInterval(loadSchedules, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [loadSchedules]);

  const handleCreate = async () => {
    if (!taskName || !engine || !cronExpr.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await createSchedule({
        task_name: taskName,
        engine,
        group: currentGroup || 'common',
        cron_expr: cronExpr.trim(),
      });
      loadSchedules();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create schedule');
    } finally {
      setSubmitting(false);
    }
  };

  const toggleEnabled = async (schedule: Schedule) => {
    try {
      await updateSchedule(schedule.id, { enabled: !schedule.enabled });
      loadSchedules();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update schedule');
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteSchedule(id);
      loadSchedules();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete schedule');
    }
  };

  const handleRunNow = async (id: string) => {
    try {
      await runScheduleNow(id);
      loadSchedules();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to run schedule');
    }
  };

  return (
    <div className="flex gap-4 h-full">
      <div className="w-80 shrink-0 glass-card p-5 space-y-4">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">
          <Clock className="w-4 h-4" /> New Schedule
        </div>

        <div>
          <label className="text-xs text-slate-400 font-medium block mb-1">Task</label>
          <select
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
        </div>

        <button
          onClick={() => void handleCreate()}
          disabled={submitting || !taskName || !engine || !cronExpr.trim()}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-primary text-white rounded-lg text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed hover:scale-[1.02] active:scale-95 transition-all"
        >
          <Plus className="w-4 h-4" /> Create Schedule
        </button>
      </div>

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
            <p className="text-sm text-slate-400 text-center py-8">
              No schedules yet. Create one to run a task automatically.
            </p>
          )}
          {schedules.map(schedule => (
            <div
              key={schedule.id}
              className={`glass-card p-4 border-slate-100 flex items-center gap-3 ${
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
                <div className="flex items-center gap-2">
                  <span className="font-medium text-sm text-slate-800 truncate">
                    {schedule.task_name}
                  </span>
                  <span className="text-[10px] px-1.5 py-0.5 bg-slate-100 text-slate-500 rounded font-mono">
                    {schedule.engine}
                  </span>
                  <span className="text-[10px] px-1.5 py-0.5 bg-slate-100 text-slate-500 rounded font-mono">
                    {schedule.cron_expr}
                  </span>
                </div>
                <div className="text-xs text-slate-400 mt-0.5 flex items-center gap-3">
                  <span>Next: {formatTimestamp(schedule.next_run_at)}</span>
                  {schedule.last_run_status && (
                    <span>
                      Last: {schedule.last_run_status} ({formatTimestamp(schedule.last_run_at)})
                    </span>
                  )}
                </div>
              </div>

              <button
                onClick={() => void handleRunNow(schedule.id)}
                title="Run now"
                className="shrink-0 p-1.5 text-slate-400 hover:text-primary transition-colors"
              >
                <Play className="w-4 h-4" />
              </button>
              <button
                onClick={() => void handleDelete(schedule.id)}
                title="Delete"
                className="shrink-0 p-1.5 text-slate-400 hover:text-red-500 transition-colors"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
