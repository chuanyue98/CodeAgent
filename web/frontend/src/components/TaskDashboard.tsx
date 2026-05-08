import React, { useCallback, useEffect, useState } from 'react';
import {
  Activity,
  CheckCircle2,
  Circle,
  Clock,
  AlertCircle,
  ChevronRight,
  ArrowLeft,
  FileText,
  Layers,
} from 'lucide-react';

interface Stage {
  name: string;
  status: string;
  goal: string;
}

interface Task {
  name: string;
  title: string;
  description: string;
  hasStages: boolean;
  stages: Stage[];
  content?: string;
}

const STATUS_DONE = ['已完成', 'DONE', '无需修改'];
const STATUS_WIP = ['进行中', 'IN_PROGRESS', '等待 CI 中', 'PR 审核中', 'IN PROGRESS'];

function stageIcon(status: string) {
  if (STATUS_DONE.includes(status))
    return <div className="p-2 bg-primary/10 rounded-xl"><CheckCircle2 className="w-4 h-4 text-primary" /></div>;
  if (STATUS_WIP.includes(status))
    return <div className="p-2 bg-amber-50 rounded-xl"><Clock className="w-4 h-4 text-amber-500 animate-spin-slow" /></div>;
  return <div className="p-2 bg-slate-100 rounded-xl"><Circle className="w-4 h-4 text-slate-300" /></div>;
}

function stageBadge(status: string) {
  if (STATUS_DONE.includes(status))
    return 'border-primary/20 text-primary bg-primary/10';
  if (STATUS_WIP.includes(status))
    return 'border-amber-200 text-amber-600 bg-amber-50 animate-pulse';
  return 'border-slate-100 text-slate-400 bg-slate-50';
}

function StageProgress({ stages }: { stages: Stage[] }) {
  const done = stages.filter(s => STATUS_DONE.includes(s.status)).length;
  const pct = stages.length > 0 ? Math.round((done / stages.length) * 100) : 0;
  return (
    <div className="flex items-center gap-2 mt-1">
      <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div className="h-full bg-primary rounded-full transition-all duration-700" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[10px] text-slate-400 font-medium w-8 text-right">{pct}%</span>
    </div>
  );
}

function TaskList({ tasks, onSelect }: { tasks: Task[]; onSelect: (name: string) => void }) {
  if (tasks.length === 0)
    return (
      <div className="flex items-center justify-center h-full text-slate-400">
        <p className="text-sm font-medium">No tasks found.</p>
      </div>
    );

  return (
    <div className="p-8 max-w-3xl mx-auto space-y-8 pb-20">
      <div className="flex justify-between items-end pb-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight flex items-center gap-3">
            <Activity className="w-8 h-8 text-primary" />
            Tasks
          </h1>
          <p className="text-sm text-slate-500 mt-1">{tasks.length} tasks available</p>
        </div>
      </div>

      <div className="grid gap-4">
        {tasks.map(task => (
          <button
            key={task.name}
            onClick={() => onSelect(task.name)}
            className="glass-card p-6 text-left hover:bg-slate-50/50 border-slate-100 transition-all group flex items-start gap-4"
          >
            <div className="p-2.5 bg-slate-100 rounded-xl group-hover:bg-primary/10 transition-colors flex-shrink-0 mt-0.5">
              {task.hasStages
                ? <Layers className="w-5 h-5 text-slate-400 group-hover:text-primary transition-colors" />
                : <FileText className="w-5 h-5 text-slate-400 group-hover:text-primary transition-colors" />}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between gap-2">
                <h3 className="font-semibold text-slate-900 truncate">{task.title}</h3>
                <ChevronRight className="w-4 h-4 text-slate-300 group-hover:text-primary flex-shrink-0 transition-colors" />
              </div>
              {task.description && (
                <p className="text-sm text-slate-500 mt-0.5 line-clamp-2">{task.description}</p>
              )}
              {task.hasStages && <StageProgress stages={task.stages} />}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

function TaskDetail({ task, onBack }: { task: Task; onBack: () => void }) {
  const done = task.stages.filter(s => STATUS_DONE.includes(s.status)).length;
  const pct = task.stages.length > 0 ? Math.round((done / task.stages.length) * 100) : 0;

  return (
    <div className="p-8 max-w-3xl mx-auto space-y-6 pb-20">
      <button onClick={onBack} className="flex items-center gap-2 text-sm text-slate-500 hover:text-primary transition-colors">
        <ArrowLeft className="w-4 h-4" />
        Back
      </button>

      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{task.title}</h1>
        {task.description && <p className="text-sm text-slate-500 mt-1">{task.description}</p>}
      </div>

      {task.hasStages && (
        <>
          <section className="glass-card p-6 space-y-4 border-slate-100">
            <div className="flex justify-between items-end">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Progress</span>
              <span className="text-3xl font-semibold text-primary tracking-tighter">{pct}%</span>
            </div>
            <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
              <div className="h-full bg-primary rounded-full transition-all duration-700" style={{ width: `${pct}%` }} />
            </div>
            <p className="text-xs text-slate-400">{done} / {task.stages.length} stages completed</p>
          </section>

          <section className="space-y-3">
            <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wider">Stages</h2>
            {task.stages.map((stage, i) => (
              <div
                key={i}
                className={`glass-card p-5 flex items-start gap-4 border transition-all ${
                  STATUS_WIP.includes(stage.status)
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

      {!task.hasStages && task.content && (
        <section className="glass-card p-6 border-slate-100">
          <pre className="text-sm text-slate-700 whitespace-pre-wrap font-sans leading-relaxed">{task.content}</pre>
        </section>
      )}
    </div>
  );
}

const TaskDashboard: React.FC = () => {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [selected, setSelected] = useState<Task | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchTasks = useCallback(async () => {
    try {
      const res = await fetch('/api/tasks');
      if (!res.ok) throw new Error('Failed to fetch tasks');
      setTasks(await res.json());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error');
    } finally {
      setLoading(false);
    }
  }, []);

  const openTask = useCallback(async (name: string) => {
    try {
      const res = await fetch(`/api/tasks/${name}`);
      if (!res.ok) throw new Error('Failed to fetch task');
      setSelected(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error');
    }
  }, []);

  useEffect(() => {
    void fetchTasks();
    const id = setInterval(() => void fetchTasks(), 10000);
    return () => clearInterval(id);
  }, [fetchTasks]);

  if (loading)
    return (
      <div className="flex items-center justify-center h-full text-slate-400">
        <Activity className="w-6 h-6 animate-spin-slow" />
      </div>
    );

  if (error)
    return (
      <div className="p-8 flex items-center justify-center h-full">
        <div className="glass-card p-6 flex items-center gap-3 bg-red-50/50 border-red-100 text-red-500">
          <AlertCircle className="w-5 h-5" />
          <span className="font-medium text-sm">{error}</span>
        </div>
      </div>
    );

  if (selected)
    return <TaskDetail task={selected} onBack={() => setSelected(null)} />;

  return <TaskList tasks={tasks} onSelect={openTask} />;
};

export default TaskDashboard;
