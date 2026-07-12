/**
 * Centralized references to the fixture data seeded by e2e/start-server.sh
 * (and re-seeded on every reset by core/web/routers/e2e.py). Keeping these
 * here means a fixture rename touches one file, not fifteen specs.
 */

export const SKILLS = {
  base: ['e2e-smoke-skill', 'e2e-logger-skill'],
  web: ['e2e-fetch-skill'],
} as const;

export const HOOKS = {
  pre: { id: 'base/e2e-pre-hook', name: 'E2E Pre Hook', event: 'pre_run' },
  post: { id: 'base/e2e-post-hook', name: 'E2E Post Hook', event: 'post_run' },
} as const;

export const PLUGINS = {
  base: 'e2e-base-plugin',
  devops: 'e2e-devops-plugin',
} as const;

export const PROMPT_GROUPS = {
  review: 'e2e-review-group',
  summarize: 'e2e-summarize-group',
} as const;

export const TASKS = ['smoke-test', 'db-migrate', 'report-gen'] as const;
