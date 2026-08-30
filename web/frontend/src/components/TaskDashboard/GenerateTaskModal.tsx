import { useRef, useState } from 'react';
import { useIsMounted } from '../../hooks/useAsyncGuards';
import { Loader2, Sparkles, StopCircle, X } from 'lucide-react';
import request from '../../utils/request';
import Modal from '../shared/Modal';
import Button from '../shared/Button';
import ErrorBar from '../shared/ErrorBar';
import { Field, Input, Select, Textarea } from '../shared/Field';
import { NAME_PATTERN, type Engine, type RunPollResponse, type Task } from './types';
import { useT } from '../../i18n/context';

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
  const t = useT();
  const [name, setName] = useState('');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [engine, setEngine] = useState(engines[0]?.id || 'opencode');
  const [phase, setPhase] = useState<'form' | 'generating' | 'failed'>('form');
  const [error, setError] = useState<string | null>(null);
  const [runId, setRunId] = useState<string | null>(null);

  const nameValid = NAME_PATTERN.test(name);

  const isMounted = useIsMounted();
  const cancelled = useRef(false);

  const handleSubmit = async () => {
    if (!nameValid || !title.trim() || !description.trim()) return;
    setError(null);
    cancelled.current = false;
    setPhase('generating');
    try {
      const status = await request<{ taskId: string }>('/api/tasks/generate', {
        method: 'POST',
        body: JSON.stringify({ engine, name, title, description }),
      });
      if (!isMounted()) return;
      setRunId(status.taskId);

      const poll = async () => {
        if (cancelled.current) return;
        try {
          const { status: runStatus } = await request<RunPollResponse>(`/api/tasks/runs/${status.taskId}`);
          if (!isMounted() || cancelled.current) return;

          if (runStatus.status === 'running') {
            setTimeout(() => void poll(), GENERATE_POLL_MS);
            return;
          }
          const tasks = await request<Task[]>('/api/tasks').catch(() => []);
          if (!isMounted() || cancelled.current) return;

          if (tasks.some(t => t.name === name)) {
            onCreated(name);
          } else {
            setError(t('taskModal.aiIncomplete', { status: runStatus.status }));
            setPhase('failed');
          }
        } catch (e) {
          if (!isMounted() || cancelled.current) return;
          setError(e instanceof Error ? e.message : t('taskModal.generateFailed'));
          setPhase('failed');
        }
      };
      void poll();
    } catch (e) {
      if (!isMounted()) return;
      setError(e instanceof Error ? e.message : t('taskModal.generateFailed'));
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
    if (!isMounted()) return;
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
    <Modal onClose={closeModal} ariaLabel={t('taskModal.generateAria')}>
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold tracking-tight flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-primary" /> {t('taskModal.generateTitle')}
        </h2>
        <button onClick={closeModal} aria-label={t('common.close')} className="p-1 text-slate-400 hover:text-slate-700 transition-colors">
          <X className="w-5 h-5" />
        </button>
      </div>

      {phase === 'generating' && (
        <div className="flex flex-col items-center justify-center gap-3 py-10 text-slate-500">
          <Loader2 className="w-8 h-8 animate-spin text-primary" />
          <p className="text-sm">{t('taskModal.writing', { engine, name })}</p>
          <Button variant="destructive" icon={StopCircle} className="mt-2" onClick={() => void cancelGeneration()}>
            {t('common.cancel')}
          </Button>
        </div>
      )}

      {phase !== 'generating' && (
        <>
          {error && <ErrorBar message={error} />}

          <div className="grid grid-cols-2 gap-3">
            <Field label={t('taskModal.fileName')} htmlFor="gen-task-name" error={name && !nameValid ? t('taskModal.nameRule') : undefined}>
              <Input
                id="gen-task-name"
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="daily-audit"
                className="font-mono"
              />
            </Field>
            <Field label={t('taskModal.title')} htmlFor="gen-task-title">
              <Input
                id="gen-task-title"
                value={title}
                onChange={e => setTitle(e.target.value)}
                placeholder={t('taskModal.titlePlaceholder')}
              />
            </Field>
          </div>

          <Field label={t('taskModal.describe')} htmlFor="gen-task-description">
            <Textarea
              id="gen-task-description"
              value={description}
              onChange={e => setDescription(e.target.value)}
              placeholder={t('taskModal.describePlaceholder')}
              rows={5}
              className="resize-y"
            />
          </Field>

          <Field label={t('filters.engine')} htmlFor="gen-task-engine">
            <Select
              id="gen-task-engine"
              value={engine}
              onChange={e => setEngine(e.target.value)}
            >
              {engines.map(e => (
                <option key={e.id} value={e.id}>{e.name}</option>
              ))}
            </Select>
          </Field>

          <div className="flex justify-end gap-3 pt-2">
            <Button variant="outline" onClick={onClose}>{t('common.cancel')}</Button>
            <Button
              icon={Sparkles}
              disabled={!nameValid || !title.trim() || !description.trim()}
              onClick={() => void handleSubmit()}
            >
              {phase === 'failed' ? t('taskModal.tryAgain') : t('taskModal.generate')}
            </Button>
          </div>
        </>
      )}
    </Modal>
  );
}
