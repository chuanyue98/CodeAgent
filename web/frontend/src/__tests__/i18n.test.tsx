import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, test, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router';
import LanguageSwitcher from '../components/LanguageSwitcher';
import { ProjectProvider } from '../context/ProjectContext';
import { LanguageProvider } from '../i18n/LanguageProvider';
import { useT } from '../i18n/context';
import { en } from '../i18n/locales/en';
import { zh } from '../i18n/locales/zh';
import {
  DEFAULT_LANGUAGE,
  interpolate,
  normalizeLanguage,
  resolveInitialLanguage,
} from '../i18n/language';

/** Every `{placeholder}` a template expects, so both locales can be compared. */
function placeholders(template: string): string[] {
  return [...template.matchAll(/\{(\w+)\}/g)].map(match => match[1]).sort();
}

describe('locale dictionaries stay in sync', () => {
  test('zh covers exactly the keys en defines', () => {
    // Typing zh as Record<TranslationKey, string> already catches a missing
    // key at build time; this catches the other direction — a stale key left
    // behind in zh after it was removed from en.
    expect(Object.keys(zh).sort()).toEqual(Object.keys(en).sort());
  });

  test('every translation takes the same placeholders as its source', () => {
    const mismatched = Object.keys(en).filter(
      key => placeholders(en[key as keyof typeof en]).join() !== placeholders(zh[key as keyof typeof en]).join(),
    );
    // A translation that drops {count} silently prints a sentence with a hole
    // in it, which no type can catch.
    expect(mismatched).toEqual([]);
  });

  test('no translation is left as the untranslated English string', () => {
    // Brand names and shared symbols legitimately match; anything else that is
    // byte-identical is almost certainly an untranslated copy-paste.
    const BRANDS = new Set(['nav.agent', 'tab.settings.mcp', 'language.en', 'language.zh']);
    const identical = Object.keys(en).filter(
      key => !BRANDS.has(key) && en[key as keyof typeof en] === zh[key as keyof typeof en],
    );
    expect(identical).toEqual([]);
  });
});

describe('language resolution', () => {
  test('normalizes locales down to a supported code', () => {
    expect(normalizeLanguage('zh-CN')).toBe('zh');
    expect(normalizeLanguage('en_US')).toBe('en');
    expect(normalizeLanguage('EN')).toBe('en');
  });

  test('treats the legacy "decide for me" values as no preference', () => {
    // config.json shipped these before `language` did anything (core/i18n.py
    // keeps the same list) — they must not be read as a real choice.
    for (const value of ['', 'auto', 'hybrid', 'system', null, undefined]) {
      expect(normalizeLanguage(value)).toBeNull();
    }
  });

  test('rejects languages we have no dictionary for', () => {
    expect(normalizeLanguage('fr')).toBeNull();
  });

  test('prefers the cache, then the browser, then the default', () => {
    expect(resolveInitialLanguage('zh', ['en-US'])).toBe('zh');
    expect(resolveInitialLanguage(null, ['fr-FR', 'zh-CN'])).toBe('zh');
    expect(resolveInitialLanguage(null, [])).toBe(DEFAULT_LANGUAGE);
  });

  test('leaves a placeholder visible when its variable is missing', () => {
    // Printing "undefined" would look like real copy; a visible {count} does not.
    expect(interpolate('{count} sessions', {})).toBe('{count} sessions');
    expect(interpolate('{count} sessions', { count: 3 })).toBe('3 sessions');
  });
});

function Label() {
  const t = useT();
  return <p>{t('nav.home')}</p>;
}

describe('LanguageProvider', () => {
  test('translates through the pinned language', () => {
    render(
      <LanguageProvider initialLanguage="zh">
        <Label />
      </LanguageProvider>,
    );
    expect(screen.getByText(zh['nav.home'])).toBeInTheDocument();
  });

  test('a component with no provider still renders, in the default language', () => {
    // The app-wide ErrorBoundary sits outside the provider by design.
    render(<Label />);
    expect(screen.getByText(en['nav.home'])).toBeInTheDocument();
  });
});

describe('LanguageSwitcher', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  test('switching repaints the UI and persists the choice to config.json', async () => {
    const calls: Array<{ url: string; body: unknown }> = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (init?.method === 'POST') {
        calls.push({ url, body: JSON.parse(String(init.body)) });
        return new Response(JSON.stringify({ status: 'success' }), { status: 200 });
      }
      const empty = url.includes('/api/config') ? {} : [];
      return new Response(JSON.stringify(empty), { status: 200 });
    });

    render(
      <MemoryRouter>
        <ProjectProvider>
          <LanguageProvider initialLanguage="en">
            <LanguageSwitcher />
            <Label />
          </LanguageProvider>
        </ProjectProvider>
      </MemoryRouter>,
    );

    expect(screen.getByText(en['nav.home'])).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('language-switcher'));
    fireEvent.click(screen.getByRole('option', { name: /中文/ }));

    // Repaints immediately rather than waiting on the write to land.
    expect(screen.getByText(zh['nav.home'])).toBeInTheDocument();

    // The setting is shared with the CLI (core/i18n.py reads the same field),
    // so it has to reach config.json, not just browser storage.
    await waitFor(() => {
      const write = calls.find(call => call.url.includes('/api/config'));
      expect(write?.body).toMatchObject({ language: 'zh' });
    });
    expect(localStorage.getItem('ca.language')).toBe('zh');
  });
});
