import { test, expect } from '../lib/test-base';
import { resetBackend } from '../lib/reset';
import {
  gotoResource,
  resourceCategory,
  resourceKind,
  resourceCard,
  resourceToggle,
  typeResourceSearch,
  backFromResourceDetail,
  resourceDetailToggle,
} from '../lib/ui';
import { SKILLS, HOOKS, PLUGINS, PROMPT_GROUPS } from '../lib/fixtures';

/**
 * Covers the Resources page, which replaced the four separate
 * skills/prompts/hooks/plugins galleries. The old per-gallery specs asserted
 * against pages that no longer exist; the scenarios they covered live on here,
 * with the one behavioural change the merge introduced: search now spans every
 * kind instead of filtering the category you happen to be in.
 */

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

// ── Sidebar: kind > category ───────────────────────────────────────────────

test('the sidebar lists every kind with its item count', async ({ page }) => {
  await page.goto('/settings/resources');

  // 3 skills, 2 hooks, 2 plugins, 2 prompt groups in the fixtures.
  await expect(resourceKind(page, 'Skills')).toContainText('3');
  await expect(resourceKind(page, 'Hooks')).toContainText('2');
  await expect(resourceKind(page, 'Plugins')).toContainText('2');
  await expect(resourceKind(page, 'Prompts')).toContainText('2');
});

test('categories render with per-category counts', async ({ page }) => {
  await gotoResource(page, 'Skills', 'base');

  // skills/base holds two fixtures, skills/web one.
  await expect(resourceCategory(page, 'Skills', 'web')).toContainText('1');
  await expect(resourceCategory(page, 'Skills', 'base')).toContainText('2');
});

test('switching category updates the listed items', async ({ page }) => {
  await gotoResource(page, 'Skills', 'base');
  await expect(resourceCard(page, SKILLS.base[0])).toBeVisible();

  await resourceCategory(page, 'Skills', 'web').click();
  await expect(resourceCard(page, SKILLS.web[0])).toBeVisible();
  await expect(resourceCard(page, SKILLS.base[0])).toHaveCount(0);
});

// ── The four kinds each render their fixtures ──────────────────────────────

test('skills render in their category', async ({ page }) => {
  await gotoResource(page, 'Skills', 'base');
  await expect(resourceCard(page, SKILLS.base[0])).toBeVisible();
  await expect(resourceCard(page, SKILLS.base[1])).toBeVisible();
});

test('both fixture hooks render', async ({ page }) => {
  await gotoResource(page, 'Skills', 'base');
  await typeResourceSearch(page, 'E2E');
  await expect(resourceCard(page, HOOKS.pre.name)).toBeVisible();
  await expect(resourceCard(page, HOOKS.post.name)).toBeVisible();
});

test('both fixture plugins render', async ({ page }) => {
  await gotoResource(page, 'Plugins', 'devops');
  await expect(resourceCard(page, PLUGINS.devops)).toBeVisible();

  await resourceCategory(page, 'Plugins', 'base').click();
  await expect(resourceCard(page, PLUGINS.base)).toBeVisible();
});

test('both fixture prompt groups render', async ({ page }) => {
  // A prompt group is an item, not a category: prompts expose a single "All"
  // category holding every group.
  await gotoResource(page, 'Prompts', 'All');
  await expect(resourceCard(page, PROMPT_GROUPS.review)).toBeVisible();
  await expect(resourceCard(page, PROMPT_GROUPS.summarize)).toBeVisible();
});

// ── Search ─────────────────────────────────────────────────────────────────

test('search matches across every kind, not just the open category', async ({
  page,
}) => {
  await gotoResource(page, 'Skills', 'base');
  await typeResourceSearch(page, 'e2e-logger');

  await expect(resourceCard(page, 'e2e-logger-skill')).toBeVisible();
  await expect(resourceCard(page, SKILLS.base[0])).toHaveCount(0);
});

test('search reaches a kind other than the one selected', async ({ page }) => {
  // Start in a skills category, then search for a plugin: the old per-gallery
  // search could never have found this.
  await gotoResource(page, 'Skills', 'base');
  await typeResourceSearch(page, PLUGINS.devops);
  await expect(resourceCard(page, PLUGINS.devops)).toBeVisible();
});

test('search with no match shows the empty state', async ({ page }) => {
  await gotoResource(page, 'Skills', 'base');
  await typeResourceSearch(page, 'zzzz-nope');
  await expect(page.locator('main')).toContainText('Nothing matches your search.');
});

// ── Detail view ────────────────────────────────────────────────────────────

test('clicking a card opens the detail view, back returns to the list', async ({
  page,
}) => {
  await gotoResource(page, 'Skills', 'base');
  await resourceCard(page, SKILLS.base[0]).click();

  await expect(
    page.getByRole('heading', { level: 1, name: SKILLS.base[0], exact: true }),
  ).toBeVisible();

  await backFromResourceDetail(page);
  await expect(resourceCard(page, SKILLS.base[0])).toBeVisible();
});

test('a prompt group detail lists the files in the group', async ({ page }) => {
  await gotoResource(page, 'Prompts', 'All');
  await resourceCard(page, PROMPT_GROUPS.review).click();

  await expect(
    page.getByRole('heading', { level: 1, name: PROMPT_GROUPS.review, exact: true }),
  ).toBeVisible();
  await expect(page.locator('main')).toContainText('Files in Group');
});

// ── Toggling ───────────────────────────────────────────────────────────────

test('toggling a skill on and off updates the switch and the card', async ({
  page,
}) => {
  await gotoResource(page, 'Skills', 'base');
  const card = resourceCard(page, SKILLS.base[0]);
  const toggle = resourceToggle(page, SKILLS.base[0]);

  // Inactive cards get a muted surface; the switch carries the real state.
  await expect(toggle).not.toBeChecked();
  await expect(card).toHaveClass(/bg-slate-50\/60/);

  await toggle.click();
  await expect(toggle).toBeChecked();
  await expect(card).not.toHaveClass(/bg-slate-50\/60/);

  await toggle.click();
  await expect(toggle).not.toBeChecked();
  await expect(card).toHaveClass(/bg-slate-50\/60/);
});

test('toggling a hook on and off updates active state', async ({ page }) => {
  await gotoResource(page, 'Skills', 'base');
  await typeResourceSearch(page, HOOKS.pre.name);

  const toggle = resourceToggle(page, HOOKS.pre.name);
  await expect(toggle).not.toBeChecked();
  await toggle.click();
  await expect(toggle).toBeChecked();
  await toggle.click();
  await expect(toggle).not.toBeChecked();
});

test('a toggle flipped in the detail view is reflected back on the card', async ({
  page,
}) => {
  await gotoResource(page, 'Skills', 'base');
  await resourceCard(page, SKILLS.base[1]).click();

  await expect(page.locator('main')).toContainText('Skill Detail');
  const detailToggle = resourceDetailToggle(page, 'skill');
  await expect(detailToggle).not.toBeChecked();
  await detailToggle.click();
  await expect(detailToggle).toBeChecked();

  await backFromResourceDetail(page);
  await expect(resourceToggle(page, SKILLS.base[1])).toBeChecked();
});
