import { useState } from 'react';
import { Plus, X } from 'lucide-react';
import request from '../../utils/request';
import Modal from '../shared/Modal';
import Button from '../shared/Button';
import ErrorBar from '../shared/ErrorBar';
import { Field, Input, Textarea } from '../shared/Field';
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

      {error && <ErrorBar message={error} />}

      <div className="grid grid-cols-2 gap-3">
        <Field label={t('taskModal.fileName')} htmlFor="new-task-name" error={name && !nameValid ? t('taskModal.nameRule') : undefined}>
          <Input
            id="new-task-name"
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="daily-audit"
            className="font-mono"
          />
        </Field>
        <Field label={t('taskModal.title')} htmlFor="new-task-title">
          <Input
            id="new-task-title"
            value={title}
            onChange={e => setTitle(e.target.value)}
            placeholder={t('taskModal.titlePlaceholder')}
          />
        </Field>
      </div>

      {[
        [t('taskModal.objective'), objective, setObjective, t('taskModal.objectivePlaceholder')],
        [t('taskModal.context'), context, setContext, t('taskModal.contextPlaceholder')],
        [t('taskModal.instructions'), instructions, setInstructions, t('taskModal.instructionsPlaceholder')],
        [t('taskModal.verification'), verification, setVerification, t('taskModal.verificationPlaceholder')],
      ].map(([label, value, setter, placeholder]) => (
        <Field key={label as string} label={label as string}>
          <Textarea
            value={value as string}
            onChange={e => (setter as (v: string) => void)(e.target.value)}
            placeholder={placeholder as string}
            rows={2}
            className="resize-y"
          />
        </Field>
      ))}

      <div className="flex justify-end gap-3 pt-2">
        <Button variant="outline" onClick={onClose}>{t('common.cancel')}</Button>
        <Button
          icon={Plus}
          loading={submitting}
          disabled={!nameValid || !title.trim()}
          onClick={() => void handleSubmit()}
        >
          {t('taskModal.create')}
        </Button>
      </div>
    </Modal>
  );
}
