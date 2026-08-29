import { type Page, type Locator, expect } from '@playwright/test';

/**
 * High-level UI interaction helpers shared across the E2E specs. These are
 * deliberately thin (no full Page-Object model — YAGNI for this surface):
 * each wraps a selector/sequence that repeats across multiple pages so a
 * layout change touches one place, not fifteen specs.
 */

/**
 * Waits for a page to have mounted.
 *
 * A leaf route is named by whichever link carries aria-current: the section's
 * tab in SectionLayout, or — for a section with no tabs, like Home — its entry
 * in the primary nav. The h1 above the tab row names the *section*, so it no
 * longer identifies which page rendered.
 */
export async function waitForPage(page: Page, label: string): Promise<void> {
  const exact = new RegExp(`^${label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`);
  await expect(
    page.locator('a[aria-current="page"]').filter({ hasText: exact }).first(),
  ).toBeVisible();
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

/** Returns the list-card element whose subtree contains `text` — used to
 *  locate a specific skill/plugin/prompt/hook card. Cards come in two visual
 *  weights since ab36ddc: `.glass-card` (panels) and `.glass-card-flat`
 *  (long galleries), so both are matched here. */
export function cardByText(page: Page, text: string): Locator {
  return page.locator('div.glass-card, div.glass-card-flat', { hasText: text });
}

// ── Resources page (ResourceHub) ─────────────────────────────────────────
// The four galleries (skills/prompts/hooks/plugins) are one page now: a
// `kind > category` sidebar on the left, cards on the right, and a search box
// that spans every kind rather than only the current category.

/** The `kind > category` sidebar, scoped by its "Library" heading so the
 *  locators below cannot stray into the app's own navigation. */
function resourceSidebar(page: Page): Locator {
  return page
    .locator('div.glass-card')
    .filter({ has: page.getByRole('heading', { name: 'Library', exact: true }) });
}

/** A kind header ("Skills", "Prompts", ...), which also carries that kind's
 *  item count. Kind headers are the only collapsible rows in the sidebar, so
 *  `aria-expanded` distinguishes them from the category rows beneath. */
export function resourceKind(page: Page, kind: string): Locator {
  return resourceSidebar(page)
    .locator('button[aria-expanded]')
    .filter({ hasText: new RegExp(`^${kind}`, 'i') });
}

/** A category row beneath `kind`. Category names are not unique across kinds
 *  — `base` exists under skills, hooks *and* plugins — so a category is only
 *  addressable relative to the kind that owns it. */
export function resourceCategory(page: Page, kind: string, category: string): Locator {
  return resourceKind(page, kind)
    .locator('xpath=following-sibling::div[1]')
    .getByRole('button', { name: new RegExp(`^${category}`, 'i') });
}

/** Opens the Resources page and selects `kind > category` in the sidebar. */
export async function gotoResource(
  page: Page,
  kind: string,
  category: string,
): Promise<void> {
  await page.goto('/settings/resources');
  await waitForPage(page, 'Resources');
  // Kind groups start expanded, so the category rows are already visible;
  // clicking the kind header would collapse the group instead.
  await resourceCategory(page, kind, category).click();
}

/** Types into the Resources search box, addressed by its label: this page has
 *  several inputs (per-card checkboxes) and search is not simply the first. */
export async function typeResourceSearch(page: Page, term: string): Promise<void> {
  const box = page.getByLabel('Search all resources');
  await box.click();
  await box.fill(term);
}

/** A resource card — a `role="button"` glass-card (flat variant since ab36ddc)
 *  whose heading is the item name. Matching the heading rather than the card's
 *  text keeps one fixture name from also selecting another that contains it. */
export function resourceCard(page: Page, name: string): Locator {
  return page
    .locator('div.glass-card[role="button"], div.glass-card-flat[role="button"]')
    .filter({ has: page.getByRole('heading', { level: 2, name, exact: true }) });
}

/** The active/inactive switch on a resource card. */
export function resourceToggle(page: Page, name: string): Locator {
  return page.getByRole('switch', { name: `Toggle ${name} active status`, exact: true });
}

/** The detail view's switch. It is labelled by the kind's noun ("Activate
 *  skill") rather than by the item name, so it needs its own locator. */
export function resourceDetailToggle(page: Page, noun: string): Locator {
  return page.getByRole('switch', {
    name: new RegExp(`^(Activate|Deactivate) ${noun}$`),
  });
}

/** Leaves a resource detail view. */
export async function backFromResourceDetail(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Back to the resource list' }).click();
}
