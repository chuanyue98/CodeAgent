import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Activity, AlertCircle } from 'lucide-react';
import { useProject } from '../../context/ProjectContext';
import { useT } from '../../i18n/context';
import {
  getRunStatus,
  getTask,
  listEngines,
  listRuns,
  listTaskRuns,
  listTasks,
  runTask,
  stopRun,
} from '../../api/tasks';
import GenerateTaskModal from './GenerateTaskModal';
import NewTaskModal from './NewTaskModal';
import TaskDetail from './TaskDetail';
import TaskList from './TaskList';
import type { Task } from './types';

const IDLE_POLL_MS = 5000;
const ACTIVE_POLL_MS = 2000;

const TaskDashboard = () => {
  const t = useT();
  const queryClient = useQueryClient();
  // Which task's detail is open. The detail, its run history and the active
  // run's poll are all derived queries keyed off this plus activeRunId --
  // closing the detail (null) disables them automatically.
  const [selectedName, setSelectedName] = useState<string | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  // Progress streamed by the active-run poll, layered over the cached detail
  // so a live run updates stages without re-fetching the task file.
  const [progress, setProgress] = useState<Partial<Task>>({});
  const [error, setError] = useState<string | null>(null);
  const [showNewTask, setShowNewTask] = useState(false);
  const [showGenerateTask, setShowGenerateTask] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
  const {
    currentGroup,
    projects,
    selectedWorkspace: workspace,
    setSelectedWorkspace: setWorkspace,
  } = useProject();

  const tasksQuery = useQuery({
    queryKey: ['tasks'],
    queryFn: listTasks,
    refetchInterval: activeRunId ? false : IDLE_POLL_MS,
  });
  const runsQuery = useQuery({
    queryKey: ['taskRuns'],
    queryFn: listRuns,
    refetchInterval: activeRunId ? false : IDLE_POLL_MS,
  });
  const enginesQuery = useQuery({ queryKey: ['engines'], queryFn: listEngines });

  const detailQuery = useQuery({
    queryKey: ['task', selectedName, currentGroup],
    queryFn: () => getTask(selectedName!, currentGroup),
    enabled: !!selectedName,
  });
  const historyQuery = useQuery({
    queryKey: ['taskHistory', selectedName],
    queryFn: () => listTaskRuns(selectedName!),
    enabled: !!selectedName,
    refetchInterval: activeRunId ? false : IDLE_POLL_MS,
  });
  const activeRunQuery = useQuery({
    queryKey: ['runStatus', activeRunId],
    queryFn: () => getRunStatus(activeRunId!),
    enabled: !!activeRunId,
    refetchInterval: ACTIVE_POLL_MS,
    // Starting a run seeds this cache from the run response; the fresh seed
    // suppresses the immediate initial fetch so the first poll waits one
    // interval, matching the old usePolling(immediate: false) cadence.
    staleTime: ACTIVE_POLL_MS,
  });

  const tasks = useMemo(() => tasksQuery.data ?? [], [tasksQuery.data]);
  const runs = useMemo(() => runsQuery.data ?? [], [runsQuery.data]);

  // A finished or failed poll clears the active run; the disabled query then
  // stops polling on its own.
  const pollData = activeRunQuery.data;
  useEffect(() => {
    if (!pollData) return;
    if (Object.keys(pollData.progress).length > 0) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setProgress(prev => ({ ...prev, ...pollData.progress }));
    }
    if (pollData.status.status !== 'running') {
      setActiveRunId(null);
    }
  }, [pollData]);

  // Starting/stopping a run is exactly when the surrounding lists go stale:
  // mirror the old effect that re-fetched tasks/runs/history whenever
  // activeRunId changed. A finished run is a new history row, and the idle
  // poll is paused while one is active, so this also covers "refresh the
  // moment the run clears".
  const previousActiveRunId = useRef<string | null>(null);
  useEffect(() => {
    if (previousActiveRunId.current !== activeRunId) {
      void queryClient.invalidateQueries({ queryKey: ['tasks'] });
      void queryClient.invalidateQueries({ queryKey: ['taskRuns'] });
      if (selectedName) {
        void queryClient.invalidateQueries({ queryKey: ['taskHistory', selectedName] });
      }
    }
    previousActiveRunId.current = activeRunId;
  }, [activeRunId, selectedName, queryClient]);

  // Run/stop errors used to be cleared by the next successful list poll; the
  // idle poll still succeeds every 5s, so keep that forgiveness.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => setError(null), [tasksQuery.dataUpdatedAt]);

  const openTask = useCallback((name: string) => {
    setProgress({});
    setSelectedName(name);
    // A run for this task may already be going (e.g. started by batch-run):
    // attach to it so the detail shows its live log.
    const active = runsQuery.data?.find(
      run => run.taskId.startsWith(name) && run.status === 'running',
    );
    setActiveRunId(active ? active.taskId : null);
  }, [runsQuery.data]);

  // Deep link from the command palette: `?task=<name>` opens that task's
  // detail once the task list has loaded, then clears the param so it
  // doesn't reopen if the user picks a different task afterward.
  useEffect(() => {
    const taskName = searchParams.get('task');
    if (taskName && tasks.some(item => item.name === taskName)) {
      // Consuming the deep link means adopting it into local state -- that
      // is the synchronization this effect exists for.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      openTask(taskName);
      setSearchParams(
        params => {
          params.delete('task');
          return params;
        },
        { replace: true },
      );
    }
  }, [tasks, searchParams, openTask, setSearchParams]);

  const runMutation = useMutation({
    mutationFn: (engine: string) => {
      const project = projects.find(item => item.path === workspace);
      return runTask(selectedName!, {
        engine,
        group: project?.group || 'common',
        workspace,
      });
    },
    onSuccess: status => {
      queryClient.setQueryData(['runStatus', status.taskId], { status, progress: {} });
      setActiveRunId(status.taskId);
    },
    onError: e => setError(e instanceof Error ? e.message : t('tasks.runFailed')),
  });

  const handleRun = (engine: string) => {
    if (!selectedName || !workspace) {
      setError(t('tasks.selectWorkspaceFirst'));
      return;
    }
    runMutation.mutate(engine);
  };

  const stopMutation = useMutation({
    mutationFn: stopRun,
    onSuccess: () => setActiveRunId(null),
    onError: e => console.error('Failed to stop task', e),
  });

  if (tasksQuery.isLoading)
    return (
      <div className="flex items-center justify-center h-full text-slate-400">
        <Activity className="w-6 h-6 animate-spin-slow" />
      </div>
    );

  const fatalMessage =
    error
    ?? (tasksQuery.error instanceof Error ? tasksQuery.error.message : tasksQuery.error ? t('tasks.error') : null)
    ?? (detailQuery.error instanceof Error ? detailQuery.error.message : detailQuery.error ? t('tasks.error') : null);

  if (fatalMessage)
    return (
      <div className="p-8 flex items-center justify-center h-full">
        <div className="glass-card p-6 flex items-center gap-3 bg-red-50/50 border-red-100 text-red-500">
          <AlertCircle className="w-5 h-5" />
          <span className="font-medium text-sm">{fatalMessage}</span>
        </div>
      </div>
    );

  const activeRun = activeRunId ? runs.find(run => run.taskId === activeRunId) : undefined;

  const selected = selectedName && detailQuery.data
    ? (Object.keys(progress).length > 0 ? { ...detailQuery.data, ...progress } : detailQuery.data)
    : null;

  if (selected)
    return (
      <TaskDetail
        task={selected}
        engines={enginesQuery.data ?? []}
        activeRun={activeRun}
        runHistory={historyQuery.data ?? []}
        onBack={() => setSelectedName(null)}
        onRun={handleRun}
        onStop={id => stopMutation.mutate(id)}
        onDeleted={() => {
          setSelectedName(null);
          void queryClient.invalidateQueries({ queryKey: ['tasks'] });
        }}
        onTaskUpdated={updated =>
          queryClient.setQueryData(['task', updated.name, currentGroup], updated)}
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
            void queryClient.invalidateQueries({ queryKey: ['tasks'] });
            openTask(name);
          }}
        />
      )}
      {showGenerateTask && (
        <GenerateTaskModal
          engines={enginesQuery.data ?? []}
          onClose={() => setShowGenerateTask(false)}
          onCreated={name => {
            setShowGenerateTask(false);
            void queryClient.invalidateQueries({ queryKey: ['tasks'] });
            openTask(name);
          }}
        />
      )}
    </>
  );
};

export default TaskDashboard;
