import { test, expect, type Page } from '@playwright/test';
import { resetBackend } from '../lib/reset';
import { waitForH2, typeSearch, cardByText, toggleInCard } from '../lib/ui';
import { HOOKS } from '../lib/fixtures';

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

async function gotoHooks(page: Page): Promise<void> {
  await page.goto('/hooks');
  await waitForH2(page, 'Hooks');
  await expect(cardByText(page, HOOKS.pre.name)).toBeVisible();
}

test('renders both fixture hooks', async ({ page }) => {
  await gotoHooks(page);
  await expect(cardByText(page, HOOKS.pre.name)).toBeVisible();
  await expect(cardByText(page, HOOKS.post.name)).toBeVisible();
});

test('search filters by name / description / event', async ({ page }) => {
  await gotoHooks(page);
  await typeSearch(page, HOOKS.pre.event); // "pre_run"
  await expect(cardByText(page, HOOKS.pre.name)).toBeVisible();
  await expect(cardByText(page, HOOKS.post.name)).toHaveCount(0);
});

test('toggling a hook on and off updates active state', async ({ page }) => {
  await gotoHooks(page);
  const card = cardByText(page, HOOKS.pre.name);
  const toggle = card.locator('button').first();

  await expect(card).toHaveClass(/opacity-70/);
  await expect(toggle).toHaveClass(/bg-slate-200/);

  await toggleInCard(card);
  await expect(toggle).toHaveClass(/bg-primary/);
  await expect(card).not.toHaveClass(/opacity-70/);

  await toggleInCard(card);
  await expect(toggle).toHaveClass(/bg-slate-200/);
});
