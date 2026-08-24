import { Loader2, Sparkles } from 'lucide-react';
import { TASK_TEMPLATES, type TaskTemplate } from '../../data/taskTemplates';
import { useT } from '../../i18n/context';

export interface TaskTemplateGalleryProps {
  /** Id of the template currently being created, if any. */
  busyId: string | null;
  onUse: (template: TaskTemplate) => void;
}

/**
 * The cards shown where an empty schedule list used to show one sentence.
 *
 * Presentational on purpose: creating the task and prefilling the form is the
 * page's job, because the page owns the form state the new task lands in.
 */
export default function TaskTemplateGallery({ busyId, onUse }: TaskTemplateGalleryProps) {
  const t = useT();

  return (
    <div>
      <div className="mb-3">
        <p className="flex items-center gap-1.5 text-sm font-semibold text-slate-700">
          <Sparkles className="h-4 w-4 text-primary" /> {t('template.sectionTitle')}
        </p>
        <p className="mt-0.5 text-xs text-slate-400">{t('template.sectionHint')}</p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-3">
        {TASK_TEMPLATES.map(template => {
          const busy = busyId === template.id;
          return (
            <div
              key={template.id}
              className="flex flex-col rounded-xl border border-slate-100 p-4 transition-colors hover:border-primary/40 hover:bg-primary/[0.03]"
            >
              <p className="text-sm font-medium text-slate-700">{t(template.titleKey)}</p>
              <p className="mt-1 flex-1 text-xs leading-relaxed text-slate-500">
                {t(template.descriptionKey)}
              </p>
              <div className="mt-3 flex items-center justify-between gap-2">
                <code className="rounded bg-slate-50 px-1.5 py-0.5 font-mono text-[10px] text-slate-500">
                  {t('template.suggestedCron', { expr: template.cronExpr })}
                </code>
                <button
                  onClick={() => onUse(template)}
                  disabled={busyId !== null}
                  className="flex shrink-0 items-center gap-1 rounded-md border border-slate-200 px-2 py-1 text-xs font-medium text-slate-600 transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {busy && <Loader2 className="h-3 w-3 animate-spin" />}
                  {busy ? t('template.creating') : t('template.use')}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
