export type ThemeChoice = 'system' | 'light' | 'dark';

const KEY = 'ca.theme';

export function readTheme(): ThemeChoice {
  try {
    const value = localStorage.getItem(KEY);
    return value === 'light' || value === 'dark' ? value : 'system';
  } catch {
    // Private windows and blocked site data throw on access; the OS setting applies.
    return 'system';
  }
}

/** "system" removes the attribute so prefers-color-scheme decides. */
export function applyTheme(choice: ThemeChoice): void {
  const root = document.documentElement;
  if (choice === 'system') root.removeAttribute('data-theme');
  else root.setAttribute('data-theme', choice);
  try {
    if (choice === 'system') localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, choice);
  } catch {
    // Not persisted; the choice still holds for this page load.
  }
}
