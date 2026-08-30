import { useState } from 'react';
import { Save, X } from 'lucide-react';
import request from '../../utils/request';
import Modal from '../shared/Modal';
import Button from '../shared/Button';
import ErrorBar from '../shared/ErrorBar';
import { Field, Textarea } from '../shared/Field';
import type { Task } from './types';
import { useT } from '../../i18n/context';

export default function EditTaskModal({
  task,
  onClose,
  onSaved,
}: {
  task: Task;
  onClose: () => void;
  onSaved: (updated: Task) => void;
}) {
  const t = useT();
  const [content, setContent] = useState(task.content ?? '');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!content.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const updated = await request<Task>(`/api/tasks/${task.name}`, {
        method: 'PUT',
        body: JSON.stringify({ content }),
      });
      onSaved(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : t('taskModal.updateFailed'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      onClose={onClose}
      ariaLabel={t('taskModal.editAria')}
      overlayClassName="pt-[8vh] overflow-y-auto"
      panelClassName="max-w-2xl p-6 space-y-4 mb-[8vh]"
    >
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold tracking-tight">{t('taskModal.editTitle')}</h2>
        <button onClick={onClose} aria-label={t('common.close')} className="p-1 text-slate-400 hover:text-slate-700 transition-colors">
          <X className="w-5 h-5" />
        </button>
      </div>

      {error && <ErrorBar message={error} />}

      <Field label={t('taskModal.contentLabel')} htmlFor="edit-task-content">
        <Textarea
          id="edit-task-content"
          value={content}
          onChange={e => setContent(e.target.value)}
          rows={20}
          className="p-3 font-mono resize-y"
        />
      </Field>

      <div className="flex justify-end gap-3 pt-2">
        <Button variant="outline" onClick={onClose}>{t('common.cancel')}</Button>
        <Button icon={Save} loading={submitting} disabled={!content.trim()} onClick={() => void handleSubmit()}>
          {t('common.save')}
        </Button>
      </div>
    </Modal>
  );
}
