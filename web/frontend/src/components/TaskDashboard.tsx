import React, { useCallback, useEffect, useRef, useState } from 'react';
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
  Plus,
  X,
  Sparkles,
  Loader2,
} from 'lucide-react';
import { useProject } from '../context/ProjectContext';
import LogViewer from './LogViewer';

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
  workspace?: string;
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

const NAME_PATTERN = /^[\w.-]+$/;
const GENERATE_POLL_MS = 2000;

function GenerateTaskModal({
  engines,
  onClose,
  onCreated,
}: {
  engines: Engine[];
  onClose: () => void;
  onCreated: (name: string) => void;
}) {
  const [name, setName] = useState('');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [engine, setEngine] = useState(engines[0]?.id || 'opencode');
  const [phase, setPhase] = useState<'form' | 'generating' | 'failed'>('form');
  const [error, setError] = useState<string | null>(null);
  const [runId, setRunId] = useState<string | null>(null);

  const nameValid = NAME_PATTERN.test(name);

  const isMounted = useRef(true);
  const cancelled = useRef(false);
  useEffect(() => {
    return () => {
      isMounted.current = false;
    };
  }, []);

  const handleSubmit = async () => {
    if (!nameValid || !title.trim() || !description.trim()) return;
    setError(null);
    cancelled.current = false;
    setPhase('generating');
    try {
      const res = await fetch('/api/tasks/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ engine, name, title, description }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Failed to start generation (${res.status})`);
      }
      const status: { task_id: string } = await res.json();
      if (!isMounted.current) return;
      setRunId(status.task_id);

      const poll = async () => {
        if (cancelled.current) return;
        try {
          const runRes = await fetch(`/api/tasks/runs/${status.task_id}`);
          if (!runRes.ok) throw new Error('Lost track of the generation run');
          const { status: runStatus } = await runRes.json();
          if (!isMounted.current || cancelled.current) return;

          if (runStatus.status === 'running') {
            setTimeout(() => void poll(), GENERATE_POLL_MS);
            return;
          }
          const tasksRes = await fetch('/api/tasks');
          const tasks: { name: string }[] = tasksRes.ok ? await tasksRes.json() : [];
          if (!isMounted.current || cancelled.current) return;

          if (tasks.some(t => t.name === name)) {
            onCreated(name);
          } else {
            setError(`AI did not finish writing the task file (run status: ${runStatus.status}). Try again, or fill it in manually.`);
            setPhase('failed');
          }
        } catch (e) {
          if (!isMounted.current || cancelled.current) return;
          setError(e instanceof Error ? e.message : 'Failed to generate task');
          setPhase('failed');
        }
      };
      void poll();
    } catch (e) {
      if (!isMounted.current) return;
      setError(e instanceof Error ? e.message : 'Failed to generate task');
      setPhase('failed');
    }
  };

  const cancelGeneration = async () => {
    cancelled.current = true;
    if (runId) {
      try {
        const res = await fetch(`/api/tasks/runs/${runId}/stop`, { method: 'POST' });
        if (!res.ok) console.error('Failed to stop generation run', res.status);
      } catch (e) {
        console.error('Failed to stop generation run', e);
      }
    }
    if (!isMounted.current) return;
    setError(null);
    setPhase('form');
  };

  const closeModal = () => {
    if (phase === 'generating') {
      void cancelGeneration();
    } else {
      onClose();
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-slate-900/40 pt-[10vh] overflow-y-auto"
      role="presentation"
      onClick={closeModal}
      onKeyDown={event => {
        if (event.key === 'Escape') closeModal();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Generate task with AI"
        className="glass-card w-full max-w-xl p-6 space-y-4 mb-[10vh]"
        onClick={event => event.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold tracking-tight flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-primary" /> Generate Task with AI
          </h2>
          <button onClick={closeModal} aria-label="Close" className="p-1 text-slate-400 hover:text-slate-700 transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        {phase === 'generating' && (
          <div className="flex flex-col items-center justify-center gap-3 py-10 text-slate-500">
            <Loader2 className="w-8 h-8 animate-spin text-primary" />
            <p className="text-sm">{engine} is writing tasks/{name}.md…</p>
            <button
              onClick={() => void cancelGeneration()}
              className="flex items-center gap-2 px-4 py-2 mt-2 bg-red-50 text-red-600 rounded-xl text-sm font-bold border border-red-100 hover:bg-red-100 transition-colors"
            >
              <StopCircle className="w-4 h-4" />
              Cancel
            </button>
          </div>
        )}

        {phase !== 'generating' && (
          <>
            {error && (
              <div className="p-3 bg-destructive/10 border border-destructive/20 text-destructive rounded-xl text-sm">
                {error}
              </div>
            )}

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="gen-task-name" className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                  File name
                </label>
                <input
                  id="gen-task-name"
                  value={name}
                  onChange={e => setName(e.target.value)}
                  placeholder="daily-audit"
                  className="mt-1 w-full p-2 border border-slate-200 rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary/20"
                />
                {name && !nameValid && (
                  <p className="text-[10px] text-red-500 mt-1">Letters, digits, dot, dash, underscore only.</p>
                )}
              </div>
              <div>
                <label htmlFor="gen-task-title" className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                  Title
                </label>
                <input
                  id="gen-task-title"
                  value={title}
                  onChange={e => setTitle(e.target.value)}
                  placeholder="Daily Code Audit"
                  className="mt-1 w-full p-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                />
              </div>
            </div>

            <div>
              <label htmlFor="gen-task-description" className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                Describe what this task should do
              </label>
              <textarea
                id="gen-task-description"
                value={description}
                onChange={e => setDescription(e.target.value)}
                placeholder="e.g. Every morning, scan the repo for leftover TODO comments and summarize file + line for each one."
                rows={5}
                className="mt-1 w-full p-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 resize-y"
              />
            </div>

            <div>
              <label htmlFor="gen-task-engine" className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                Engine
              </label>
              <select
                id="gen-task-engine"
                value={engine}
                onChange={e => setEngine(e.target.value)}
                className="mt-1 w-full p-2 border border-slate-200 rounded-lg bg-white text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
              >
                {engines.map(e => (
                  <option key={e.id} value={e.id}>{e.name}</option>
                ))}
              </select>
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <button
                onClick={onClose}
                className="px-4 py-2 border border-slate-200 text-slate-600 rounded-xl text-sm font-medium hover:bg-slate-50 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => void handleSubmit()}
                disabled={!nameValid || !title.trim() || !description.trim()}
                className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-xl text-sm font-semibold disabled:opacity-50 hover:opacity-90 transition-all"
              >
                <Sparkles className="w-4 h-4" /> {phase === 'failed' ? 'Try Again' : 'Generate'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function NewTaskModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (name: string) => void;
}) {
  const [name, setName] = useState('');
  const [title, setTitle] = useState('');
  const [objective, setObjective] = useState('');
  const [context, setContext] = useState('');
  const [instructions, setInstructions] = useState('');
  const [verification, setVerification] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const nameValid = NAME_PATTERN.test(name);

  const handleSubmit = async () => {
    if (!nameValid || !title.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch('/api/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, title, objective, context, instructions, verification }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Failed to create task (${res.status})`);
      }
      onCreated(name);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create task');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-slate-900/40 pt-[8vh] overflow-y-auto"
      role="presentation"
      onClick={onClose}
      onKeyDown={event => {
        if (event.key === 'Escape') onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="New task"
        className="glass-card w-full max-w-xl p-6 space-y-4 mb-[8vh]"
        onClick={event => event.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold tracking-tight">New Task</h2>
          <button onClick={onClose} aria-label="Close" className="p-1 text-slate-400 hover:text-slate-700 transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        {error && (
          <div className="p-3 bg-destructive/10 border border-destructive/20 text-destructive rounded-xl text-sm">
            {error}
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label htmlFor="new-task-name" className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              File name
            </label>
            <input
              id="new-task-name"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="daily-audit"
              className="mt-1 w-full p-2 border border-slate-200 rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary/20"
            />
            {name && !nameValid && (
              <p className="text-[10px] text-red-500 mt-1">Letters, digits, dot, dash, underscore only.</p>
            )}
          </div>
          <div>
            <label htmlFor="new-task-title" className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Title
            </label>
            <input
              id="new-task-title"
              value={title}
              onChange={e => setTitle(e.target.value)}
              placeholder="Daily Code Audit"
              className="mt-1 w-full p-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
            />
          </div>
        </div>

        {[
          ['Objective (目标)', objective, setObjective, 'What should this task accomplish?'],
          ['Context (背景)', context, setContext, 'Background the engine needs to know.'],
          ['Instructions (指令)', instructions, setInstructions, 'Concrete, actionable steps.'],
          ['Verification (验证)', verification, setVerification, 'How to confirm the task succeeded.'],
        ].map(([label, value, setter, placeholder]) => (
          <div key={label as string}>
            <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider">{label as string}</label>
            <textarea
              value={value as string}
              onChange={e => (setter as (v: string) => void)(e.target.value)}
              placeholder={placeholder as string}
              rows={2}
              className="mt-1 w-full p-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 resize-y"
            />
          </div>
        ))}

        <div className="flex justify-end gap-3 pt-2">
          <button
            onClick={onClose}
            className="px-4 py-2 border border-slate-200 text-slate-600 rounded-xl text-sm font-medium hover:bg-slate-50 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => void handleSubmit()}
            disabled={submitting || !nameValid || !title.trim()}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-xl text-sm font-semibold disabled:opacity-50 hover:opacity-90 transition-all"
          >
            <Plus className="w-4 h-4" /> Create Task
          </button>
        </div>
      </div>
    </div>
  );
}

function TaskList({
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
  return (
    <div className="p-8 max-w-3xl mx-auto space-y-8 pb-20">
      <div className="flex justify-between items-end pb-4">
        <div>
          <h2 className="text-3xl font-semibold tracking-tight flex items-center gap-3">
            <Activity className="w-8 h-8 text-primary" />
            Tasks
          </h2>
          <p className="text-sm text-slate-500 mt-1">{tasks.length} tasks available</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={onManualCreateClick}
            title="Write the task file by hand"
            className="flex items-center gap-2 px-3 py-2.5 border border-slate-200 text-slate-600 rounded-xl hover:bg-slate-50 transition-all font-semibold text-sm"
          >
            <Plus className="w-4 h-4" /> Manual
          </button>
          <button
            onClick={onGenerateClick}
            className="flex items-center gap-2 px-4 py-2.5 bg-primary text-white rounded-xl hover:opacity-90 transition-all font-semibold shadow-lg shadow-primary/20 active:scale-95 text-sm"
          >
            <Sparkles className="w-4 h-4" /> Generate with AI
          </button>
        </div>
      </div>

      {tasks.length === 0 && (
        <div className="flex items-center justify-center py-16 text-slate-400">
          <p className="text-sm font-medium">No tasks found. Create one to get started.</p>
        </div>
      )}

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
                    <h2 className="font-semibold text-slate-900 truncate">{task.title}</h2>
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
  onStop,
  workspace,
  projects,
  onWorkspaceChange,
}: {
  task: Task;
  engines: Engine[];
  activeRun?: RunStatus;
  onBack: () => void;
  onRun: (engine: string) => void;
  onStop: (id: string) => void;
  workspace: string;
  projects: { path: string; group: string; available?: boolean }[];
  onWorkspaceChange: (workspace: string) => void;
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
                aria-label="Workspace"
                value={workspace}
                onChange={e => onWorkspaceChange(e.target.value)}
                className="max-w-56 bg-white border border-slate-200 rounded-xl px-3 py-2 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-primary/20"
              >
                <option value="" disabled>Select workspace</option>
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
                Run Task
              </button>
            </>
          )}
        </div>
      </div>

      <div className="flex justify-between items-start">
        <div className="flex-1">
          <h2 className="text-2xl font-semibold tracking-tight text-slate-900 flex items-center gap-3">
            {task.title}
            {activeRun && (
              <span className="flex items-center gap-1.5 px-3 py-1 bg-emerald-50 text-emerald-600 rounded-full text-xs font-bold uppercase tracking-wider border border-emerald-100 animate-pulse">
                Running
              </span>
            )}
          </h2>
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

          {activeRun && (
            <section className="space-y-3">
              <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wider flex items-center gap-2">
                <Terminal className="w-4 h-4" />
                Execution Logs
              </h2>
              <div className="rounded-xl overflow-hidden border border-slate-200" style={{ height: 400 }}>
                <LogViewer taskId={activeRun.task_id} />
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
  const [showNewTask, setShowNewTask] = useState(false);
  const [showGenerateTask, setShowGenerateTask] = useState(false);
  const { currentGroup, projects } = useProject();
  const [workspace, setWorkspace] = useState('');

  useEffect(() => {
    if (!workspace || !projects.some(project => project.path === workspace && project.available !== false)) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setWorkspace(projects.find(project => project.available !== false)?.path || '');
    }
  }, [projects, workspace]);

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
    if (!selected || !workspace) {
      setError('Select a workspace before running a task');
      return;
    }
    try {
      const project = projects.find(item => item.path === workspace);
      const res = await fetch(`/api/tasks/${selected.name}/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ engine, group: project?.group || 'common', workspace })
      });
      if (res.ok) {
        const status: RunStatus = await res.json();
        setActiveRunId(status.task_id);
        void fetchRuns();
      } else {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Task failed to start (${res.status})`);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to run task');
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
    let mounted = true;

    const init = async () => {
      await fetchTasks();
      if (mounted) {
        await fetchRuns();
        await fetchEngines();
      }
    };

    void init();

    if (activeRunId) return;
    const id = setInterval(() => {
      void fetchTasks();
      void fetchRuns();
    }, 5000);

    return () => {
      mounted = false;
      clearInterval(id);
    };
  }, [fetchTasks, fetchRuns, fetchEngines, activeRunId]);

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
        workspace={workspace}
        projects={projects}
        onWorkspaceChange={setWorkspace}
      />
    );

  return (
    <>
      <TaskList
        tasks={tasks}
        runs={runs}
        onSelect={openTask}
        onManualCreateClick={() => setShowNewTask(true)}
        onGenerateClick={() => setShowGenerateTask(true)}
      />
      {showNewTask && (
        <NewTaskModal
          onClose={() => setShowNewTask(false)}
          onCreated={name => {
            setShowNewTask(false);
            void fetchTasks();
            void openTask(name);
          }}
        />
      )}
      {showGenerateTask && (
        <GenerateTaskModal
          engines={engines}
          onClose={() => setShowGenerateTask(false)}
          onCreated={name => {
            setShowGenerateTask(false);
            void fetchTasks();
            void openTask(name);
          }}
        />
      )}
    </>
  );
};

export default TaskDashboard;
