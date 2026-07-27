import { useState } from 'react';
import { Plus, X } from 'lucide-react';
import request from '../../utils/request';
import Modal from '../shared/Modal';
import { NAME_PATTERN } from './types';

export default function NewTaskModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (name: string) => void;
}) {
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
      setError(e instanceof Error ? e.message : 'Failed to create task');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      onClose={onClose}
      ariaLabel="New task"
      overlayClassName="pt-[8vh] overflow-y-auto"
      panelClassName="max-w-xl p-6 space-y-4 mb-[8vh]"
    >
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold tracking-tight">New Task</h2>
        <button onClick={onClose} aria-label="Close" className="p-1 text-slate-400 hover:text-slate-700 transition-colors">
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
            File name
          </label>
          <input
            id="new-task-name"
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="daily-audit"
            className="mt-1 w-full p-2 border border-slate-200 rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary/20"
          />
          {name && !nameValid && (
            <p className="text-[10px] text-red-500 mt-1">Letters, digits, dot, dash, underscore only.</p>
          )}
        </div>
        <div>
          <label htmlFor="new-task-title" className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            Title
          </label>
          <input
            id="new-task-title"
            value={title}
            onChange={e => setTitle(e.target.value)}
            placeholder="Daily Code Audit"
            className="mt-1 w-full p-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
          />
        </div>
      </div>

      {[
        ['Objective (目标)', objective, setObjective, 'What should this task accomplish?'],
        ['Context (背景)', context, setContext, 'Background the engine needs to know.'],
        ['Instructions (指令)', instructions, setInstructions, 'Concrete, actionable steps.'],
        ['Verification (验证)', verification, setVerification, 'How to confirm the task succeeded.'],
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
          Cancel
        </button>
        <button
          onClick={() => void handleSubmit()}
          disabled={submitting || !nameValid || !title.trim()}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-xl text-sm font-semibold disabled:opacity-50 hover:opacity-90 transition-all"
        >
          <Plus className="w-4 h-4" /> Create Task
        </button>
      </div>
    </Modal>
  );
}
