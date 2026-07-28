import { test, expect, type Page } from '../lib/test-base';
import { resetBackend } from '../lib/reset';
import {
  waitForH2,
  typeSearch,
  cardByText,
  toggleInCard,
  openCard,
  backFromDetail,
} from '../lib/ui';
import { SKILLS } from '../lib/fixtures';

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

async function gotoSkills(page: Page): Promise<void> {
  await page.goto('/skills');
  await waitForH2(page, 'Skills');
  // Categories render in API order; the first selected is not deterministic,
  // so explicitly select "base" (which holds the skills we assert on).
  await page.getByRole('button', { name: /^base/i }).click();
  await expect(cardByText(page, SKILLS.base[0])).toBeVisible();
}

test('categories render with per-category counts', async ({ page }) => {
  await gotoSkills(page);
  const webBtn = page.getByRole('button', { name: /^web/i });
  await expect(webBtn).toBeVisible();
  // web category has exactly one fixture skill -> count badge "1"
  await expect(webBtn).toContainText('1');
  const baseBtn = page.getByRole('button', { name: /^base/i });
  await expect(baseBtn).toContainText('2');
});

test('switching category updates the listed skills', async ({ page }) => {
  await gotoSkills(page);
  await page.getByRole('button', { name: /^web/i }).click();
  await expect(cardByText(page, SKILLS.web[0])).toBeVisible();
  await expect(cardByText(page, SKILLS.base[0])).toHaveCount(0);
});

test('search filters the current category', async ({ page }) => {
  await gotoSkills(page);
  await typeSearch(page, 'logger');
  await expect(cardByText(page, 'e2e-logger-skill')).toBeVisible();
  await expect(cardByText(page, 'e2e-smoke-skill')).toHaveCount(0);
});

test('search with no match shows the empty state', async ({ page }) => {
  await gotoSkills(page);
  await typeSearch(page, 'zzzz-nope');
  await expect(page.locator('main')).toContainText('No skills found');
});

test('clicking a card opens the detail view, back returns to list', async ({
  page,
}) => {
  await gotoSkills(page);
  await openCard(page, SKILLS.base[0]);
  await expect(page.locator('main')).toContainText('Skill Detail');
  await expect(page.getByRole('heading', { level: 1, name: SKILLS.base[0] })).toBeVisible();
  await backFromDetail(page);
  await expect(cardByText(page, SKILLS.base[0])).toBeVisible();
});

test('toggling a skill on/off updates the switch and card state', async ({
  page,
}) => {
  await gotoSkills(page);
  const card = cardByText(page, SKILLS.base[0]);
  const toggle = card.locator('button').first();

  // Initially inactive: card has a subtle surface treatment and the switch is grey.
  await expect(card).toHaveClass(/bg-slate-50\/60/);
  await expect(toggle).toHaveClass(/bg-slate-200/);

  await toggleInCard(card);
  await expect(toggle).toHaveClass(/bg-primary/);
  await expect(card).not.toHaveClass(/bg-slate-50\/60/);

  // Toggle off again.
  await toggleInCard(card);
  await expect(toggle).toHaveClass(/bg-slate-200/);
  await expect(card).toHaveClass(/bg-slate-50\/60/);
});
