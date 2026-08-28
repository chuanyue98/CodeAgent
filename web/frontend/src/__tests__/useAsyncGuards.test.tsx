import { StrictMode } from 'react';
import { render } from '@testing-library/react';
import { describe, expect, test } from 'vitest';
import { useIsMounted, useLatestRequest } from '../hooks/useAsyncGuards';

describe('useIsMounted', () => {
  test('reports mounted after a remount, not just on the first mount', () => {
    const captured: { isMounted?: () => boolean } = {};

    function Probe() {
      captured.isMounted = useIsMounted();
      return null;
    }

    // StrictMode mounts, unmounts, and mounts again on the same instance. A
    // ref that is only initialised to true -- never set back to it -- reads
    // false from here on, and every later response is thrown away.
    render(
      <StrictMode>
        <Probe />
      </StrictMode>,
    );

    expect(captured.isMounted?.()).toBe(true);
  });

  test('reports unmounted after the component goes away', () => {
    const captured: { isMounted?: () => boolean } = {};

    function Probe() {
      captured.isMounted = useIsMounted();
      return null;
    }

    const view = render(<Probe />);
    expect(captured.isMounted?.()).toBe(true);

    view.unmount();
    expect(captured.isMounted?.()).toBe(false);
  });
});

describe('useLatestRequest', () => {
  test('only the newest claim stays current', () => {
    const captured: { claim?: () => () => boolean } = {};

    function Probe() {
      captured.claim = useLatestRequest();
      return null;
    }

    render(<Probe />);

    const first = captured.claim!();
    expect(first()).toBe(true);

    const second = captured.claim!();
    expect(second()).toBe(true);
    // The earlier request lost its claim the moment the later one started.
    expect(first()).toBe(false);
  });
});
