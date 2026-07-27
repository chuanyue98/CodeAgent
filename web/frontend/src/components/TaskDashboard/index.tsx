import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router';
import { Activity, AlertCircle } from 'lucide-react';
import { useProject } from '../../context/ProjectContext';
import request from '../../utils/request';
import usePolling from '../../hooks/usePolling';
import GenerateTaskModal from './GenerateTaskModal';
import NewTaskModal from './NewTaskModal';
import TaskDetail from './TaskDetail';
import TaskList from './TaskList';
import type { Engine, RunPollResponse, RunStatus, Task } from './types';

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
  const [searchParams, setSearchParams] = useSearchParams();
  const {
    currentGroup,
    projects,
    selectedWorkspace: workspace,
    setSelectedWorkspace: setWorkspace,
  } = useProject();

  // Read via a ref inside pollActiveRun instead of taking `selected` as a
  // useCallback dependency — otherwise pollActiveRun (and the interval
  // effect that depends on it) would be recreated on every unrelated
  // `selected` update, resetting/drifting the poll interval.
  const selectedRef = useRef<Task | null>(selected);
  useEffect(() => {
    selectedRef.current = selected;
  }, [selected]);

  const fetchTasks = useCallback(async () => {
    try {
      setTasks(await request<Task[]>('/api/tasks'));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error');
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchRuns = useCallback(async () => {
    try {
      setRuns(await request<RunStatus[]>('/api/tasks/runs'));
    } catch (e) {
      console.error('Failed to fetch runs', e);
    }
  }, []);

  const fetchEngines = useCallback(async () => {
    try {
      setEngines(await request<Engine[]>('/api/engines'));
    } catch (e) {
      console.error('Failed to fetch engines', e);
    }
  }, []);

  const openTask = useCallback(async (name: string) => {
    try {
      const params = new URLSearchParams();
      if (currentGroup) params.append('group', currentGroup);
      const task = await request<Task>(`/api/tasks/${name}?${params.toString()}`);
      setSelected(task);

      // Check if this task is already running
      const active = runs.find(r => r.task_id.startsWith(name) && r.status === 'running');
      if (active) setActiveRunId(active.task_id);
      else setActiveRunId(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error');
    }
  }, [currentGroup, runs]);

  // Deep link from the command palette: `?task=<name>` opens that task's
  // detail once the task list has loaded, then clears the param so it
  // doesn't reopen if the user picks a different task afterward.
  useEffect(() => {
    const taskName = searchParams.get('task');
    if (taskName && tasks.some(t => t.name === taskName)) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      void openTask(taskName);
      setSearchParams(
        params => {
          params.delete('task');
          return params;
        },
        { replace: true },
      );
    }
  }, [tasks, searchParams, openTask, setSearchParams]);

  const runTask = async (engine: string) => {
    if (!selected || !workspace) {
      setError('Select a workspace before running a task');
      return;
    }
    try {
      const project = projects.find(item => item.path === workspace);
      const status = await request<RunStatus>(`/api/tasks/${selected.name}/run`, {
        method: 'POST',
        body: JSON.stringify({ engine, group: project?.group || 'common', workspace }),
      });
      setActiveRunId(status.task_id);
      void fetchRuns();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to run task');
    }
  };

  const stopTask = async (id: string) => {
    try {
      await request(`/api/tasks/runs/${id}/stop`, { method: 'POST' });
      setActiveRunId(null);
      void fetchRuns();
    } catch (e) {
      console.error('Failed to stop task', e);
    }
  };

  const pollActiveRun = useCallback(async () => {
    if (!activeRunId || !selectedRef.current) return;
    try {
      const { status, progress } = await request<RunPollResponse>(`/api/tasks/runs/${activeRunId}`);
      if (status.status !== 'running') {
        setActiveRunId(null);
      }
      setSelected(prev => prev ? { ...prev, ...progress } : null);
    } catch (e) {
      console.error('Failed to poll run', e);
    }
  }, [activeRunId]);

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

    return () => {
      mounted = false;
    };
  }, [fetchTasks, fetchRuns, fetchEngines, activeRunId]);

  // Poll the task/run list every 5s while nothing is actively running (the
  // effect above already fetches once immediately on mount and whenever
  // activeRunId changes, so this only needs to own the recurring timer).
  usePolling(() => {
    void fetchTasks();
    void fetchRuns();
  }, 5000, !activeRunId, { immediate: false });

  // Poll the active run every 2s while one is running.
  usePolling(() => void pollActiveRun(), 2000, !!activeRunId, { immediate: false });

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
