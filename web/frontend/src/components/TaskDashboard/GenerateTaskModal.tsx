import { useEffect, useRef, useState } from 'react';
import { Loader2, Sparkles, StopCircle, X } from 'lucide-react';
import request from '../../utils/request';
import Modal from '../shared/Modal';
import { NAME_PATTERN, type Engine, type RunPollResponse, type Task } from './types';

const GENERATE_POLL_MS = 2000;

export default function GenerateTaskModal({
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
      const status = await request<{ task_id: string }>('/api/tasks/generate', {
        method: 'POST',
        body: JSON.stringify({ engine, name, title, description }),
      });
      if (!isMounted.current) return;
      setRunId(status.task_id);

      const poll = async () => {
        if (cancelled.current) return;
        try {
          const { status: runStatus } = await request<RunPollResponse>(`/api/tasks/runs/${status.task_id}`);
          if (!isMounted.current || cancelled.current) return;

          if (runStatus.status === 'running') {
            setTimeout(() => void poll(), GENERATE_POLL_MS);
            return;
          }
          const tasks = await request<Task[]>('/api/tasks').catch(() => []);
          if (!isMounted.current || cancelled.current) return;

          if (tasks.some(t => t.name === name)) {
            onCreated(name);
          } else {
            setError(`AI 未完成任务文件的编写（运行状态：${runStatus.status}）。请重试，或手动填写。`);
            setPhase('failed');
          }
        } catch (e) {
          if (!isMounted.current || cancelled.current) return;
          setError(e instanceof Error ? e.message : '生成任务失败');
          setPhase('failed');
        }
      };
      void poll();
    } catch (e) {
      if (!isMounted.current) return;
      setError(e instanceof Error ? e.message : '生成任务失败');
      setPhase('failed');
    }
  };

  const cancelGeneration = async () => {
    cancelled.current = true;
    if (runId) {
      try {
        await request(`/api/tasks/runs/${runId}/stop`, { method: 'POST' });
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
    <Modal onClose={closeModal} ariaLabel="AI 生成任务">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold tracking-tight flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-primary" /> AI 生成任务
        </h2>
        <button onClick={closeModal} aria-label="关闭" className="p-1 text-slate-400 hover:text-slate-700 transition-colors">
          <X className="w-5 h-5" />
        </button>
      </div>

      {phase === 'generating' && (
        <div className="flex flex-col items-center justify-center gap-3 py-10 text-slate-500">
          <Loader2 className="w-8 h-8 animate-spin text-primary" />
          <p className="text-sm">{engine} 正在编写 tasks/{name}.md…</p>
          <button
            onClick={() => void cancelGeneration()}
            className="flex items-center gap-2 px-4 py-2 mt-2 bg-red-50 text-red-600 rounded-xl text-sm font-bold border border-red-100 hover:bg-red-100 transition-colors"
          >
            <StopCircle className="w-4 h-4" />
            取消
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
                文件名
              </label>
              <input
                id="gen-task-name"
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="daily-audit"
                className="mt-1 w-full p-2 border border-slate-200 rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary/20"
              />
              {name && !nameValid && (
                <p className="text-[10px] text-red-500 mt-1">仅限字母、数字、点、连字符和下划线。</p>
              )}
            </div>
            <div>
              <label htmlFor="gen-task-title" className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                标题
              </label>
              <input
                id="gen-task-title"
                value={title}
                onChange={e => setTitle(e.target.value)}
                placeholder="每日代码审计"
                className="mt-1 w-full p-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
              />
            </div>
          </div>

          <div>
            <label htmlFor="gen-task-description" className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              描述这个任务要做什么
            </label>
            <textarea
              id="gen-task-description"
              value={description}
              onChange={e => setDescription(e.target.value)}
              placeholder="例如：每天早上扫描仓库中遗留的 TODO 注释，并汇总每处所在的文件和行号。"
              rows={5}
              className="mt-1 w-full p-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 resize-y"
            />
          </div>

          <div>
            <label htmlFor="gen-task-engine" className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              引擎
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
              取消
            </button>
            <button
              onClick={() => void handleSubmit()}
              disabled={!nameValid || !title.trim() || !description.trim()}
              className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-xl text-sm font-semibold disabled:opacity-50 hover:opacity-90 transition-all"
            >
              <Sparkles className="w-4 h-4" /> {phase === 'failed' ? '重试' : '生成'}
            </button>
          </div>
        </>
      )}
    </Modal>
  );
}
