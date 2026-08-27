import { describe, expect, test } from 'vitest';
import { buildResumeLink, buildSessionLink } from '../utils/sessionLink';

describe('session links', () => {
  test('the object view and the verb are different destinations', () => {
    const args = ['claude', 'sess-1', '/work/proj'] as const;

    expect(buildSessionLink(...args)).toMatch(/^\/activity\/sessions\?/);
    expect(buildResumeLink(...args)).toMatch(/^\/agent\/terminal\?/);
  });

  test('the resume link carries what the PTY endpoint asks for', () => {
    const params = new URLSearchParams(
      buildResumeLink('opencode', 'ses_abc', '/work/proj').split('?')[1],
    );

    // These three names are the PTY endpoint's own query contract; the
    // detail-view link deliberately uses namespaced ones instead.
    expect(params.get('engine')).toBe('opencode');
    expect(params.get('cwd')).toBe('/work/proj');
    expect(params.get('session')).toBe('ses_abc');
  });

  test('paths with spaces survive the round trip', () => {
    const params = new URLSearchParams(
      buildResumeLink('codex', 'id-1', '/work/my project').split('?')[1],
    );
    expect(params.get('cwd')).toBe('/work/my project');
  });
});
