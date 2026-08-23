import { type Page, type Locator, expect } from '@playwright/test';

/**
 * High-level UI interaction helpers shared across the E2E specs. These are
 * deliberately thin (no full Page-Object model — YAGNI for this surface):
 * each wraps a selector/sequence that repeats across multiple pages so a
 * layout change touches one place, not fifteen specs.
 */

/** Waits for a page to have mounted — every route renders its label as the
 *  primary heading in App.tsx's header, so this is the universal render signal. */
export async function waitForH2(page: Page, label: string): Promise<void> {
  await expect(page.getByRole('heading', { level: 1, name: label, exact: true })).toBeVisible();
}

/** Opens the ProjectSwitcher dropdown (click toggle) and picks a group.
 *  Drives every page whose data is re-scoped by `currentGroup`. */
export async function switchGroup(page: Page, group: string): Promise<void> {
  // Addressed by test id, not by aria-haspopup="listbox": the header now holds
  // three listbox triggers (group, workspace, language) and matching on the
  // role attribute picks up all of them.
  await page.getByTestId('group-switcher').click();
  await page.getByRole('option', { name: group, exact: true }).click();
}

/** Types into the first search box on the page (galleries, sessions, audit).
 *  Every gallery/sessions/audit search input is a plain text <input>, so the
 *  first one on the page is the search field. */
export async function typeSearch(page: Page, term: string): Promise<void> {
  const box = page.locator('input[type="text"]').first();
  await box.click();
  await box.fill(term);
}

/** Returns the list-card element (a `.glass-card`) whose subtree contains
 *  `text` — used to locate a specific skill/plugin/prompt/hook card. */
export function cardByText(page: Page, text: string): Locator {
  return page.locator('div.glass-card', { hasText: text });
}

/** Clicks the toggle switch inside a gallery card. For every gallery the
 *  first <button> in a card is its enable/disable switch. */
export async function toggleInCard(card: Locator): Promise<void> {
  await card.locator('button').first().click();
}

/** Clicks a card to open its detail view. */
export async function openCard(page: Page, text: string): Promise<void> {
  await cardByText(page, text).click({ trial: false });
}

/** Returns from a detail view via the icon-only back button (a <button>
 *  whose child svg has the `rotate-180` class in every gallery). */
export async function backFromDetail(page: Page): Promise<void> {
  await page.locator('button', { has: page.locator('svg.rotate-180') }).click();
}
