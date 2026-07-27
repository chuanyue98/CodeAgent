import { useState } from 'react';
import { ArrowLeft, BookOpen, CheckCircle2, Circle, Clock, Code, Play, StopCircle, Terminal } from 'lucide-react';
import LogViewer from '../LogViewer';
import { classifyStageStatus, type Engine, type RunStatus, type Task } from './types';

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

export default function TaskDetail({
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

  const done = task.stages.filter(s => classifyStageStatus(s.status) === 'done').length;
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
