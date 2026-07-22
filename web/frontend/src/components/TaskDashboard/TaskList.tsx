import { Activity, ChevronRight, FileText, Layers, Plus, Sparkles } from 'lucide-react';
import { STATUS_DONE, type RunStatus, type Stage, type Task } from './types';

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

export default function TaskList({
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
