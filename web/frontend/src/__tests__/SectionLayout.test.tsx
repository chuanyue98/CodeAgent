import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { describe, expect, test } from 'vitest';
import SectionLayout from '../components/SectionLayout';
import { en } from '../i18n/locales/en';
import { ACTIVITY_FILTER_PARAMS, ACTIVITY_TABS } from '../navigation';

function renderActivityTabs(initialPath: string) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route
          path="/activity"
          element={
            <SectionLayout
              labelKey="nav.activity"
              tabs={ACTIVITY_TABS}
              preserveParams={ACTIVITY_FILTER_PARAMS}
            />
          }
        >
          <Route path="sessions" element={<p>sessions</p>} />
          <Route path="timeline" element={<p>timeline</p>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

function href(name: string): string {
  return screen.getByRole('link', { name }).getAttribute('href') ?? '';
}

describe('SectionLayout preserveParams', () => {
  test('carries filter params onto every sibling tab', () => {
    // The original complaint: narrowing the view on Sessions and switching to
    // Timeline threw the filters away.
    renderActivityTabs('/activity/sessions?q=deploy&engines=claude%2Ccodex&project=%2Fwork%2Fapp');

    for (const label of ACTIVITY_TABS.map(tab => en[tab.labelKey])) {
      const target = new URL(href(label), 'http://localhost');
      expect(target.searchParams.get('q')).toBe('deploy');
      expect(target.searchParams.get('engines')).toBe('claude,codex');
      expect(target.searchParams.get('project')).toBe('/work/app');
    }
  });

  test('leaves single-session deep-link params behind', () => {
    // These identify one row to open; carrying them into a sibling tab would
    // pop a drawer the user never asked for.
    renderActivityTabs(
      '/activity/sessions?q=deploy&session=s-1&sessionEngine=claude&sessionProject=%2Fwork%2Fapp',
    );

    const target = new URL(href('Usage'), 'http://localhost');
    expect(target.searchParams.get('q')).toBe('deploy');
    expect(target.searchParams.get('session')).toBeNull();
    expect(target.searchParams.get('sessionEngine')).toBeNull();
    expect(target.searchParams.get('sessionProject')).toBeNull();
  });

  test('links stay bare when nothing is filtered', () => {
    renderActivityTabs('/activity/sessions');

    expect(href('Usage')).toBe('/activity/usage');
  });
});
