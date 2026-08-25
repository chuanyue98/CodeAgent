import { useState } from 'react';
import { Save, X } from 'lucide-react';
import request from '../../utils/request';
import Modal from '../shared/Modal';
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

      {error && (
        <div className="p-3 bg-destructive/10 border border-destructive/20 text-destructive rounded-xl text-sm">
          {error}
        </div>
      )}

      <div>
        <label htmlFor="edit-task-content" className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
          {t('taskModal.contentLabel')}
        </label>
        <textarea
          id="edit-task-content"
          value={content}
          onChange={e => setContent(e.target.value)}
          rows={20}
          className="mt-1 w-full p-3 border border-slate-200 rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary/20 resize-y"
        />
      </div>

      <div className="flex justify-end gap-3 pt-2">
        <button
          onClick={onClose}
          className="px-4 py-2 border border-slate-200 text-slate-600 rounded-xl text-sm font-medium hover:bg-slate-50 transition-colors"
        >
          {t('common.cancel')}
        </button>
        <button
          onClick={() => void handleSubmit()}
          disabled={submitting || !content.trim()}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-xl text-sm font-semibold disabled:opacity-50 hover:opacity-90 transition-all"
        >
          <Save className="w-4 h-4" /> {t('common.save')}
        </button>
      </div>
    </Modal>
  );
}
