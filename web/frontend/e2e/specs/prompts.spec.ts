import { test, expect, type Page } from '@playwright/test';
import { resetBackend } from '../lib/reset';
import {
  waitForH2,
  typeSearch,
  cardByText,
  openCard,
  backFromDetail,
} from '../lib/ui';
import { PROMPT_GROUPS } from '../lib/fixtures';

test.beforeEach(async ({ baseURL }) => {
  await resetBackend(baseURL!);
});

async function gotoPrompts(page: Page): Promise<void> {
  await page.goto('/prompts');
  await waitForH2(page, 'Prompts');
  await expect(cardByText(page, PROMPT_GROUPS.review)).toBeVisible();
}

test('renders both fixture prompt groups', async ({ page }) => {
  await gotoPrompts(page);
  await expect(cardByText(page, PROMPT_GROUPS.review)).toBeVisible();
  await expect(cardByText(page, PROMPT_GROUPS.summarize)).toBeVisible();
});

test('search filters by name / description / file', async ({ page }) => {
  await gotoPrompts(page);
  await typeSearch(page, 'review');
  await expect(cardByText(page, PROMPT_GROUPS.review)).toBeVisible();
  await expect(cardByText(page, PROMPT_GROUPS.summarize)).toHaveCount(0);
});

test('card opens detail with its file list and a working toggle', async ({
  page,
}) => {
  await gotoPrompts(page);
  await openCard(page, PROMPT_GROUPS.review);
  await expect(page.locator('main')).toContainText('Prompt Group');
  await expect(page.locator('main')).toContainText('Files in Group');
  await expect(page.getByText('review-detailed.md')).toBeVisible();

  const detailToggle = page.locator('div', { hasText: 'Active in' }).last().locator('button');
  await expect(detailToggle).toHaveClass(/bg-slate-200/);
  await detailToggle.click();
  await expect(detailToggle).toHaveClass(/bg-primary/);

  await backFromDetail(page);
  await expect(cardByText(page, PROMPT_GROUPS.review)).toBeVisible();
});
