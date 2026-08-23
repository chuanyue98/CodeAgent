import { useState } from 'react';
import { Plus, X } from 'lucide-react';
import request from '../../utils/request';
import Modal from '../shared/Modal';
import { NAME_PATTERN } from './types';
import { useT } from '../../i18n/context';

export default function NewTaskModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (name: string) => void;
}) {
  const t = useT();
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
      await request('/api/tasks', {
        method: 'POST',
        body: JSON.stringify({ name, title, objective, context, instructions, verification }),
      });
      onCreated(name);
    } catch (e) {
      setError(e instanceof Error ? e.message : t('taskModal.createFailed'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      onClose={onClose}
      ariaLabel={t('taskModal.newAria')}
      overlayClassName="pt-[8vh] overflow-y-auto"
      panelClassName="max-w-xl p-6 space-y-4 mb-[8vh]"
    >
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold tracking-tight">{t('taskModal.newTitle')}</h2>
        <button onClick={onClose} aria-label={t('common.close')} className="p-1 text-slate-400 hover:text-slate-700 transition-colors">
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
            {t('taskModal.fileName')}
          </label>
          <input
            id="new-task-name"
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="daily-audit"
            className="mt-1 w-full p-2 border border-slate-200 rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary/20"
          />
          {name && !nameValid && (
            <p className="text-[10px] text-red-500 mt-1">{t('taskModal.nameRule')}</p>
          )}
        </div>
        <div>
          <label htmlFor="new-task-title" className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            {t('taskModal.title')}
          </label>
          <input
            id="new-task-title"
            value={title}
            onChange={e => setTitle(e.target.value)}
            placeholder={t('taskModal.titlePlaceholder')}
            className="mt-1 w-full p-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
          />
        </div>
      </div>

      {[
        [t('taskModal.objective'), objective, setObjective, t('taskModal.objectivePlaceholder')],
        [t('taskModal.context'), context, setContext, t('taskModal.contextPlaceholder')],
        [t('taskModal.instructions'), instructions, setInstructions, t('taskModal.instructionsPlaceholder')],
        [t('taskModal.verification'), verification, setVerification, t('taskModal.verificationPlaceholder')],
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
          {t('common.cancel')}
        </button>
        <button
          onClick={() => void handleSubmit()}
          disabled={submitting || !nameValid || !title.trim()}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-xl text-sm font-semibold disabled:opacity-50 hover:opacity-90 transition-all"
        >
          <Plus className="w-4 h-4" /> {t('taskModal.create')}
        </button>
      </div>
    </Modal>
  );
}
