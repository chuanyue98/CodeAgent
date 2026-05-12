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
  Terminal,
  Code,
  BookOpen,
  Play,
  StopCircle,
} from 'lucide-react';
import { useProject } from '../context/ProjectContext';

interface Stage {
  name: string;
  status: string;
  goal: string;
}

interface Skill {
  name: string;
  id: string;
  description: string;
  scripts: string[];
}

interface Engine {
  id: string;
  name: string;
  description: string;
}

interface RunStatus {
  task_id: string;
  engine: string;
  status: 'running' | 'completed' | 'failed' | 'stopped';
  log_path: string;
  start_time: number;
}

interface Task {
  name: string;
  title: string;
  description: string;
  hasStages: boolean;
  stages: Stage[];
  content?: string;
  resolved_skills?: Skill[];
  resolved_prompts?: string[];
  logs?: string;
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

function TaskList({
  tasks,
  runs,
  onSelect
}: {
  tasks: Task[];
  runs: RunStatus[];
  onSelect: (name: string) => void
}) {
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
        {tasks.map(task => {
          const activeRun = runs.find(r => r.task_id.startsWith(task.name) && r.status === 'running');

          return (
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
                  <div className="flex items-center gap-3 min-w-0">
                    <h3 className="font-semibold text-slate-900 truncate">{task.title}</h3>
                    {activeRun && (
                      <span className="flex items-center gap-1.5 px-2 py-0.5 bg-emerald-50 text-emerald-600 rounded-full text-[10px] font-bold uppercase tracking-wider border border-emerald-100 animate-pulse">
                        <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full" />
                        Running on {activeRun.engine}
                      </span>
                    )}
                  </div>
                  <ChevronRight className="w-4 h-4 text-slate-300 group-hover:text-primary flex-shrink-0 transition-colors" />
                </div>
                {task.description && (
                  <p className="text-sm text-slate-500 mt-0.5 line-clamp-2">{task.description}</p>
                )}
                {task.hasStages && <StageProgress stages={task.stages} />}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function TaskDetail({
  task,
  engines,
  activeRun,
  onBack,
  onRun,
  onStop
}: {
  task: Task;
  engines: Engine[];
  activeRun?: RunStatus;
  onBack: () => void;
  onRun: (engine: string) => void;
  onStop: (id: string) => void;
}) {
  const [selectedEngine, setSelectedEngine] = useState(engines[0]?.id || 'gemini');

  const done = task.stages.filter(s => STATUS_DONE.includes(s.status)).length;
  const pct = task.stages.length > 0 ? Math.round((done / task.stages.length) * 100) : 0;

  return (
    <div className="p-8 max-w-4xl mx-auto space-y-6 pb-20">
      <div className="flex items-center justify-between">
        <button onClick={onBack} className="flex items-center gap-2 text-sm text-slate-500 hover:text-primary transition-colors">
          <ArrowLeft className="w-4 h-4" />
          Back
        </button>

        <div className="flex items-center gap-3">
          {activeRun ? (
            <button
              onClick={() => onStop(activeRun.task_id)}
              className="flex items-center gap-2 px-4 py-2 bg-red-50 text-red-600 rounded-xl text-sm font-bold border border-red-100 hover:bg-red-100 transition-colors"
            >
              <StopCircle className="w-4 h-4" />
              Stop Execution
            </button>
          ) : (
            <>
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
                Run Task
              </button>
            </>
          )}
        </div>
      </div>

      <div className="flex justify-between items-start">
        <div className="flex-1">
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900 flex items-center gap-3">
            {task.title}
            {activeRun && (
              <span className="flex items-center gap-1.5 px-3 py-1 bg-emerald-50 text-emerald-600 rounded-full text-xs font-bold uppercase tracking-wider border border-emerald-100 animate-pulse">
                Running
              </span>
            )}
          </h1>
          {task.description && <p className="text-sm text-slate-500 mt-1">{task.description}</p>}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
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

          {activeRun && task.logs && (
            <section className="space-y-3">
              <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wider flex items-center gap-2">
                <Terminal className="w-4 h-4" />
                Execution Logs
              </h2>
              <div className="glass-card bg-slate-900 border-slate-800 p-4 rounded-xl overflow-hidden">
                <pre className="text-[11px] font-mono text-emerald-400/90 whitespace-pre-wrap leading-relaxed max-h-[400px] overflow-y-auto custom-scrollbar-dark">
                  {task.logs}
                </pre>
              </div>
            </section>
          )}

          {!task.hasStages && task.content && !activeRun && (
            <section className="glass-card p-6 border-slate-100">
              <pre className="text-sm text-slate-700 whitespace-pre-wrap font-sans leading-relaxed">{task.content}</pre>
            </section>
          )}
        </div>

        <div className="space-y-6">
          <section className="space-y-3">
            <h2 className="text-xs font-bold text-slate-400 uppercase tracking-widest flex items-center gap-2">
              <Terminal className="w-3.5 h-3.5" />
              Mounted Skills
            </h2>
            <div className="space-y-2">
              {task.resolved_skills && task.resolved_skills.length > 0 ? (
                task.resolved_skills.map(skill => (
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
                  No skills mounted
                </div>
              )}
            </div>
          </section>

          <section className="space-y-3">
            <h2 className="text-xs font-bold text-slate-400 uppercase tracking-widest flex items-center gap-2">
              <BookOpen className="w-3.5 h-3.5" />
              Injected Prompts
            </h2>
            <div className="flex flex-wrap gap-2">
              {task.resolved_prompts && task.resolved_prompts.length > 0 ? (
                task.resolved_prompts.map(prompt => (
                  <span key={prompt} className="px-2 py-1 bg-primary/5 text-primary border border-primary/10 rounded-lg text-xs font-medium">
                    {prompt}
                  </span>
                ))
              ) : (
                <div className="text-xs text-slate-400 italic p-4 bg-slate-50 rounded-xl border border-dashed border-slate-200 w-full">
                  No prompts injected
                </div>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

const TaskDashboard: React.FC = () => {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [runs, setRuns] = useState<RunStatus[]>([]);
  const [engines, setEngines] = useState<Engine[]>([]);
  const [selected, setSelected] = useState<Task | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const { currentGroup } = useProject();

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

  const fetchRuns = useCallback(async () => {
    try {
      const res = await fetch('/api/tasks/runs');
      if (res.ok) {
        setRuns(await res.json());
      }
    } catch (e) {
      console.error('Failed to fetch runs', e);
    }
  }, []);

  const fetchEngines = useCallback(async () => {
    try {
      const res = await fetch('/api/engines');
      if (res.ok) {
        setEngines(await res.json());
      }
    } catch (e) {
      console.error('Failed to fetch engines', e);
    }
  }, []);

  const openTask = useCallback(async (name: string) => {
    try {
      const params = new URLSearchParams();
      if (currentGroup) params.append('group', currentGroup);
      const res = await fetch(`/api/tasks/${name}?${params.toString()}`);
      if (!res.ok) throw new Error('Failed to fetch task');
      setSelected(await res.json());

      // Check if this task is already running
      const active = runs.find(r => r.task_id.startsWith(name) && r.status === 'running');
      if (active) setActiveRunId(active.task_id);
      else setActiveRunId(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error');
    }
  }, [currentGroup, runs]);

  const runTask = async (engine: string) => {
    if (!selected) return;
    try {
      const res = await fetch(`/api/tasks/${selected.name}/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ engine, group: currentGroup || 'common' })
      });
      if (res.ok) {
        const status: RunStatus = await res.json();
        setActiveRunId(status.task_id);
        void fetchRuns();
      }
    } catch (e) {
      console.error('Failed to run task', e);
    }
  };

  const stopTask = async (id: string) => {
    try {
      const res = await fetch(`/api/tasks/runs/${id}/stop`, { method: 'POST' });
      if (res.ok) {
        setActiveRunId(null);
        void fetchRuns();
      }
    } catch (e) {
      console.error('Failed to stop task', e);
    }
  };

  const pollActiveRun = useCallback(async () => {
    if (!activeRunId || !selected) return;
    try {
      const res = await fetch(`/api/tasks/runs/${activeRunId}`);
      if (res.ok) {
        const { status, progress } = await res.json();
        if (status.status !== 'running') {
          setActiveRunId(null);
        }
        setSelected(prev => prev ? { ...prev, ...progress } : null);
      }
    } catch (e) {
      console.error('Failed to poll run', e);
    }
  }, [activeRunId, selected]);

  useEffect(() => {
    void fetchTasks();
    void fetchRuns();
    void fetchEngines();
    const id = setInterval(() => {
      void fetchTasks();
      void fetchRuns();
    }, 5000);
    return () => clearInterval(id);
  }, [fetchTasks, fetchRuns, fetchEngines]);

  useEffect(() => {
    if (activeRunId) {
      const id = setInterval(() => void pollActiveRun(), 2000);
      return () => clearInterval(id);
    }
  }, [activeRunId, pollActiveRun]);

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

  const activeRun = activeRunId ? runs.find(r => r.task_id === activeRunId) : undefined;

  if (selected)
    return (
      <TaskDetail
        task={selected}
        engines={engines}
        activeRun={activeRun}
        onBack={() => setSelected(null)}
        onRun={runTask}
        onStop={stopTask}
      />
    );

  return <TaskList tasks={tasks} runs={runs} onSelect={openTask} />;
};

export default TaskDashboard;
