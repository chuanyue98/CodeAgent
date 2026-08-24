import type { TranslationKey } from '../i18n/locales/en';

/**
 * A ready-made task blueprint plus the cron expression it is usually paired
 * with.
 *
 * The real obstacle to using schedules has never been the form — it is not
 * knowing what is worth scheduling in the first place, which left the page
 * showing an empty list and a sentence that explained nothing. Each template
 * fills the same four sections `POST /api/tasks` already accepts, so picking
 * one writes an ordinary `tasks/<name>.md` that can then be edited like any
 * hand-written task. Nothing here is a new storage format or a new concept.
 */
export interface TaskTemplate {
  /** Task file name (`tasks/<id>.md`); must match the backend's [\w.-]+ rule. */
  id: string;
  titleKey: TranslationKey;
  descriptionKey: TranslationKey;
  /** Suggested schedule. Prefilled into the form, never applied on its own. */
  cronExpr: string;
  objectiveKey: TranslationKey;
  contextKey: TranslationKey;
  instructionsKey: TranslationKey;
  verificationKey: TranslationKey;
}

/**
 * Deliberately short. A wall of templates is the same problem as an empty
 * list — these are the six that pay off on almost any repository, and they
 * are meant to be edited after they land, not used verbatim forever.
 */
export const TASK_TEMPLATES: readonly TaskTemplate[] = [
  {
    id: 'weekly-code-review',
    titleKey: 'template.codeReview.title',
    descriptionKey: 'template.codeReview.description',
    cronExpr: '0 9 * * 1',
    objectiveKey: 'template.codeReview.objective',
    contextKey: 'template.codeReview.context',
    instructionsKey: 'template.codeReview.instructions',
    verificationKey: 'template.codeReview.verification',
  },
  {
    id: 'dependency-check',
    titleKey: 'template.dependency.title',
    descriptionKey: 'template.dependency.description',
    cronExpr: '0 10 * * 1',
    objectiveKey: 'template.dependency.objective',
    contextKey: 'template.dependency.context',
    instructionsKey: 'template.dependency.instructions',
    verificationKey: 'template.dependency.verification',
  },
  {
    id: 'coverage-check',
    titleKey: 'template.coverage.title',
    descriptionKey: 'template.coverage.description',
    cronExpr: '0 8 * * *',
    objectiveKey: 'template.coverage.objective',
    contextKey: 'template.coverage.context',
    instructionsKey: 'template.coverage.instructions',
    verificationKey: 'template.coverage.verification',
  },
  {
    id: 'security-scan',
    titleKey: 'template.security.title',
    descriptionKey: 'template.security.description',
    cronExpr: '0 3 * * *',
    objectiveKey: 'template.security.objective',
    contextKey: 'template.security.context',
    instructionsKey: 'template.security.instructions',
    verificationKey: 'template.security.verification',
  },
  {
    id: 'todo-sweep',
    titleKey: 'template.todo.title',
    descriptionKey: 'template.todo.description',
    cronExpr: '0 9 1 * *',
    objectiveKey: 'template.todo.objective',
    contextKey: 'template.todo.context',
    instructionsKey: 'template.todo.instructions',
    verificationKey: 'template.todo.verification',
  },
  {
    id: 'changelog-update',
    titleKey: 'template.changelog.title',
    descriptionKey: 'template.changelog.description',
    cronExpr: '0 18 * * 5',
    objectiveKey: 'template.changelog.objective',
    contextKey: 'template.changelog.context',
    instructionsKey: 'template.changelog.instructions',
    verificationKey: 'template.changelog.verification',
  },
];
