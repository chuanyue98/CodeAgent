import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import SessionProgress from '../components/SessionProgress';
import type { SessionUsage } from '../api/analytics';
import { session as baseSession } from './factories';
import type { SessionMessage } from '../api/audit';

function message(overrides: Partial<SessionMessage> = {}): SessionMessage {
  return {
    role: 'user',
    content: 'do the thing',
    timestamp: '2026-07-20T10:00:00Z',
    model: 'claude-opus',
    toolCalls: [],
    ...overrides,
  };
}

/** Token totals drive the progress arithmetic, so they are pinned here. */
function usage(overrides: Partial<SessionUsage> = {}): SessionUsage {
  return baseSession({
    inputTokens: 1000,
    outputTokens: 500,
    cost: 0.42,
    lastActivity: '2026-07-20T10:30:00Z',
    ...overrides,
  });
}

test('a session with nothing to report renders no strip at all', () => {
  // An empty box saying nothing is worse than no box.
  const { container } = render(<SessionProgress detail={{ messages: [] }} />);

  expect(container).toBeEmptyDOMElement();
});

test('a null detail renders nothing', () => {
  const { container } = render(<SessionProgress detail={null} />);

  expect(container).toBeEmptyDOMElement();
});

test('turns count user messages, not every message', () => {
  render(
    <SessionProgress
      detail={{
        messages: [
          message({ role: 'user' }),
          message({ role: 'assistant' }),
          message({ role: 'user' }),
          message({ role: 'assistant' }),
        ],
      }}
    />,
  );

  expect(screen.getByText('2 turns')).toBeInTheDocument();
});

test('duration spans the first and last timestamp', () => {
  render(
    <SessionProgress
      detail={{
        messages: [
          message({ timestamp: '2026-07-20T10:00:00Z' }),
          message({ role: 'assistant', timestamp: '2026-07-20T11:34:00Z' }),
        ],
      }}
    />,
  );

  expect(screen.getByText('1h34m')).toBeInTheDocument();
});

test('usage totals join the strip only when the caller has them', () => {
  const { rerender } = render(<SessionProgress detail={{ messages: [message()] }} />);
  expect(screen.queryByText('$0.42')).not.toBeInTheDocument();

  rerender(<SessionProgress detail={{ messages: [message()] }} usage={usage()} />);
  expect(screen.getByText('$0.42')).toBeInTheDocument();
});

test('a free session does not advertise a zero cost', () => {
  render(
    <SessionProgress detail={{ messages: [message()] }} usage={usage({ cost: 0 })} />,
  );

  expect(screen.queryByText('$0.00')).not.toBeInTheDocument();
});

test('the last actions read newest first', () => {
  render(
    <SessionProgress
      detail={{
        messages: [
          message({
            role: 'assistant',
            toolCalls: [
              { name: 'Read', argsPreview: '{"file_path": "a.py"}', resultPreview: '' },
              { name: 'Edit', argsPreview: '{"file_path": "b.py"}', resultPreview: '' },
              { name: 'Bash', argsPreview: '{"command": "uv run pytest"}', resultPreview: '' },
            ],
          }),
        ],
      }}
    />,
  );

  const names = screen
    .getAllByText(/^(Read|Edit|Bash)$/)
    .map(node => node.textContent);
  expect(names).toEqual(['Bash', 'Edit', 'Read']);
});

test('files touched are de-duplicated and listed most recent first', () => {
  render(
    <SessionProgress
      detail={{
        messages: [
          message({
            role: 'assistant',
            toolCalls: [
              { name: 'Read', argsPreview: '{"file_path": "a.py"}', resultPreview: '' },
              { name: 'Edit', argsPreview: '{"file_path": "b.py"}', resultPreview: '' },
              { name: 'Edit', argsPreview: '{"file_path": "a.py"}', resultPreview: '' },
            ],
          }),
        ],
      }}
    />,
  );

  expect(screen.getByText('2 files')).toBeInTheDocument();
  expect(screen.getByText('a.py · b.py')).toBeInTheDocument();
});

test('a long file list keeps its full form in the tooltip', () => {
  render(
    <SessionProgress
      detail={{
        messages: [
          message({
            role: 'assistant',
            toolCalls: [
              { name: 'Edit', argsPreview: '{"file_path": "a.py"}', resultPreview: '' },
              { name: 'Edit', argsPreview: '{"file_path": "b.py"}', resultPreview: '' },
            ],
          }),
        ],
      }}
    />,
  );

  expect(screen.getByText('b.py · a.py')).toHaveAttribute('title', 'b.py\na.py');
});

test('a session that only ran tools still gets a strip', () => {
  // No user turn, no timestamps, no usage -- but the actions are worth showing.
  render(
    <SessionProgress
      detail={{
        messages: [
          message({
            role: 'assistant',
            timestamp: '',
            toolCalls: [{ name: 'Bash', argsPreview: '{"command": "ls"}', resultPreview: '' }],
          }),
        ],
      }}
    />,
  );

  expect(screen.getByTestId('session-progress')).toBeInTheDocument();
  expect(screen.getByText('Last actions')).toBeInTheDocument();
});
