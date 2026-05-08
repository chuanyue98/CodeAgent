import React, { useCallback, useEffect, useState } from 'react';
import { Activity, CheckCircle2, Circle, Clock, AlertCircle } from 'lucide-react';

interface TaskStage {
  name: string;
  status: 'DONE' | 'IN_PROGRESS' | 'TODO';
  goal: string;
}

interface TaskData {
  exists: boolean;
  tasks: TaskStage[];
}

const TaskDashboard: React.FC = () => {
  const [data, setData] = useState<TaskData | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchTasks = useCallback(async () => {
    try {
      const response = await fetch('/api/task');
      if (!response.ok) throw new Error('Failed to fetch tasks');
      const result = await response.json();
      setData(result);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchTasks();
    const interval = setInterval(() => {
      void fetchTasks();
    }, 5000);
    return () => clearInterval(interval);
  }, [fetchTasks]);

  if (error) return (
    <div className="p-8 text-red-500 flex items-center justify-center h-full">
      <div className="glass-card p-6 flex items-center gap-3 bg-red-50/50 border-red-100">
        <AlertCircle className="w-5 h-5" />
        <span className="font-medium">{error}</span>
      </div>
    </div>
  );

  if (!data) return (
    <div className="p-8 flex items-center justify-center h-full">
      <div className="flex flex-col items-center gap-4 text-slate-400 animate-pulse">
        <Activity className="w-8 h-8 animate-spin-slow" />
        <span className="text-sm font-medium">Syncing data...</span>
      </div>
    </div>
  );

  if (!data.exists) return (
    <div className="p-8 flex items-center justify-center h-full">
      <div className="text-center text-slate-400">
        <p className="text-sm font-medium">No active tasks found.</p>
      </div>
    </div>
  );

  const totalTasks = data.tasks.length;
  const doneTasks = data.tasks.filter(t => t.status === 'DONE').length;
  const progress = totalTasks > 0 ? (doneTasks / totalTasks) * 100 : 0;

  return (
    <div className="p-8 max-w-5xl mx-auto space-y-8 min-h-full pb-20">
      <div className="flex justify-between items-end pb-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight flex items-center gap-3">
            <Activity className="w-8 h-8 text-primary" />
            Task Monitor
          </h1>
          <p className="text-sm text-slate-500 mt-1">Live tracking of active operation stages</p>
        </div>
        <div className="flex items-center gap-2 text-[10px] font-bold text-primary uppercase tracking-widest bg-primary/5 px-4 py-2 rounded-full border border-primary/10">
          <div className="w-1.5 h-1.5 bg-primary rounded-full animate-pulse shadow-[0_0_8px_rgba(8,145,178,0.5)]" />
          Live Update
        </div>
      </div>

      <section className="glass-card p-10 space-y-8 relative overflow-hidden border-slate-100">
        <div className="absolute top-0 right-0 p-4 opacity-[0.03] pointer-events-none">
          <Activity size={180} />
        </div>
        <div className="flex justify-between items-end relative z-10">
          <div>
            <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Mission Progress</h2>
            <p className="text-lg font-medium text-slate-700 mt-1">{doneTasks} of {totalTasks} stages completed</p>
          </div>
          <span className="text-6xl font-semibold text-primary tracking-tighter">{Math.round(progress)}%</span>
        </div>
        <div className="w-full h-3 bg-slate-100 rounded-full relative z-10 overflow-hidden">
          <div
            className="h-full bg-primary transition-all duration-1000 ease-in-out rounded-full shadow-lg shadow-primary/20"
            style={{ width: `${progress}%` }}
          />
        </div>
      </section>

      <section className="space-y-4">
        <div className="flex items-center gap-4">
          <h2 className="text-xl font-semibold tracking-tight">Deployment Stages</h2>
          <div className="flex-1 h-px bg-slate-100" />
        </div>
        <div className="grid gap-4">
          {data.tasks.map((task, index) => (
            <div
              key={index}
              className={`glass-card p-6 transition-all ${
                task.status === 'IN_PROGRESS'
                  ? 'border-primary/20 bg-primary/5 ring-1 ring-primary/5'
                  : 'hover:bg-slate-50/50 border-slate-100'
              } flex items-start gap-6`}
            >
              <div className="mt-1 flex-shrink-0">
                {task.status === 'DONE' ? (
                  <div className="p-2.5 bg-primary/10 rounded-xl">
                    <CheckCircle2 className="w-5 h-5 text-primary" />
                  </div>
                ) : task.status === 'IN_PROGRESS' ? (
                  <div className="p-2.5 bg-primary/10 rounded-xl">
                    <Clock className="w-5 h-5 text-primary animate-spin-slow" />
                  </div>
                ) : (
                  <div className="p-2.5 bg-slate-100 rounded-xl">
                    <Circle className="w-5 h-5 text-slate-300" />
                  </div>
                )}
              </div>
              <div className="flex-1">
                <div className="flex justify-between items-start">
                  <div>
                    <h3 className="font-semibold text-lg tracking-tight text-slate-900">{task.name}</h3>
                    <p className="text-sm font-medium text-slate-500 mt-0.5">{task.goal}</p>
                  </div>
                  <span className={`text-[10px] px-3 py-1.5 rounded-lg font-bold uppercase tracking-widest border ${
                    task.status === 'DONE' ? 'border-primary/20 text-primary bg-primary/10' :
                    task.status === 'IN_PROGRESS' ? 'border-primary/30 text-primary bg-primary/10 animate-pulse' :
                    'border-slate-100 text-slate-400 bg-slate-50'
                  }`}>
                    {task.status.replace('_', ' ')}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
};

export default TaskDashboard;
