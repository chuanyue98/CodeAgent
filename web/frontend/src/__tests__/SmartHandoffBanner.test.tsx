import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';
import SmartHandoffBanner from '../components/SmartHandoffBanner';

describe('SmartHandoffBanner', () => {
  test('renders engine name and rate limit message', () => {
    render(
      <SmartHandoffBanner
        activeEngine="claude"
        onHandoff={vi.fn()}
        onDismiss={vi.fn()}
      />,
    );

    const alert = screen.getByRole('alert');
    expect(alert).toBeInTheDocument();
    expect(alert).toHaveAttribute('aria-live', 'polite');
    // Claude is the display name for 'claude'
    expect(screen.getByText(/claude/i)).toBeInTheDocument();
    expect(screen.getByText(/rate limit|quota exceeded/i)).toBeInTheDocument();
  });

  test('renders custom engine name when activeEngine is unknown brand', () => {
    render(
      <SmartHandoffBanner
        activeEngine="custom-model-ai"
        onHandoff={vi.fn()}
        onDismiss={vi.fn()}
      />,
    );

    expect(screen.getByText(/custom-model-ai/i)).toBeInTheDocument();
  });

  test('offers default quick handoff targets excluding activeEngine', () => {
    render(
      <SmartHandoffBanner
        activeEngine="claude"
        onHandoff={vi.fn()}
        onDismiss={vi.fn()}
      />,
    );

    // Active engine 'claude' should not appear in handoff target buttons
    const buttons = screen.getAllByRole('button');
    // Targets from AGENT_ENGINES like opencode / codex / codebuddy / antigravity
    const hasCodexOrOpenCode = buttons.some(
      b => /codex/i.test(b.textContent || '') || /opencode/i.test(b.textContent || ''),
    );
    expect(hasCodexOrOpenCode).toBe(true);

    const handoffClaudeBtn = screen.queryByRole('button', { name: /^claude$/i });
    expect(handoffClaudeBtn).toBeNull();
  });

  test('renders specified targetEngines when provided', () => {
    render(
      <SmartHandoffBanner
        activeEngine="claude"
        targetEngines={[
          { id: 'codex', name: 'Codex AI' },
          { id: 'antigravity', name: 'Antigravity Pro' },
        ]}
        onHandoff={vi.fn()}
        onDismiss={vi.fn()}
      />,
    );

    expect(screen.getByRole('button', { name: /codex ai/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /antigravity pro/i })).toBeInTheDocument();
  });

  test('clicking handoff button calls onHandoff with target engine id', () => {
    const onHandoff = vi.fn();
    render(
      <SmartHandoffBanner
        activeEngine="claude"
        targetEngines={[{ id: 'codex', name: 'Codex' }]}
        onHandoff={onHandoff}
        onDismiss={vi.fn()}
      />,
    );

    const codexBtn = screen.getByRole('button', { name: /codex/i });
    fireEvent.click(codexBtn);

    expect(onHandoff).toHaveBeenCalledTimes(1);
    expect(onHandoff).toHaveBeenCalledWith('codex');
  });

  test('displays loading state on button when loadingEngine matches', () => {
    render(
      <SmartHandoffBanner
        activeEngine="claude"
        targetEngines={[
          { id: 'codex', name: 'Codex' },
          { id: 'antigravity', name: 'Antigravity' },
        ]}
        loadingEngine="codex"
        onHandoff={vi.fn()}
        onDismiss={vi.fn()}
      />,
    );

    const codexBtn = screen.getByRole('button', { name: /codex/i });
    expect(codexBtn).toBeDisabled();
    expect(codexBtn).toHaveAttribute('aria-busy', 'true');
    expect(screen.getByTestId('loading-spinner')).toBeInTheDocument();

    const agBtn = screen.getByRole('button', { name: /antigravity/i });
    expect(agBtn).toBeDisabled();
    expect(agBtn).toHaveAttribute('aria-busy', 'false');
  });

  test('clicking dismiss button calls onDismiss', () => {
    const onDismiss = vi.fn();
    render(
      <SmartHandoffBanner
        activeEngine="claude"
        onHandoff={vi.fn()}
        onDismiss={onDismiss}
      />,
    );

    const dismissBtn = screen.getByTestId('smart-handoff-dismiss');
    fireEvent.click(dismissBtn);

    expect(onDismiss).toHaveBeenCalledTimes(1);
  });
});
