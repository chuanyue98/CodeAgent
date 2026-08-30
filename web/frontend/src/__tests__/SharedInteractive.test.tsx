import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';
import BatchActionBar from '../components/shared/BatchActionBar';
import ConfirmDialog from '../components/shared/ConfirmDialog';
import Modal from '../components/shared/Modal';
import Toggle from '../components/shared/Toggle';

describe('Modal', () => {
  test('clicking the backdrop closes, clicking inside does not', () => {
    const onClose = vi.fn();
    render(
      <Modal onClose={onClose} ariaLabel="Test modal">
        <p>inside content</p>
      </Modal>,
    );
    const dialog = screen.getByRole('dialog', { name: 'Test modal' });
    fireEvent.click(dialog);
    expect(onClose).not.toHaveBeenCalled();
    // The backdrop is the dialog's parent presentation layer.
    fireEvent.click(dialog.parentElement as HTMLElement);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  test('Escape inside the modal closes it', () => {
    const onClose = vi.fn();
    render(
      <Modal onClose={onClose} ariaLabel="Esc modal">
        <p>content</p>
      </Modal>,
    );
    fireEvent.keyDown(screen.getByRole('dialog', { name: 'Esc modal' }), {
      key: 'Escape',
    });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  test('ariaLabelledBy wins over ariaLabel', () => {
    render(
      <Modal onClose={vi.fn()} ariaLabel="ignored" ariaLabelledBy="heading-x">
        <h2 id="heading-x">Real title</h2>
      </Modal>,
    );
    expect(screen.getByRole('dialog', { name: 'Real title' })).toBeInTheDocument();
  });
});

describe('ConfirmDialog', () => {
  test('confirm and cancel callbacks', () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(
      <ConfirmDialog
        title="Delete it?"
        description="This cannot be undone."
        onConfirm={onConfirm}
        onCancel={onCancel}
      />,
    );
    expect(
      screen.getByRole('alertdialog', { name: 'Delete it?' }),
    ).toHaveTextContent('This cannot be undone.');

    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  test('the confirm button takes focus on open', () => {
    render(
      <ConfirmDialog
        title="Delete it?"
        description="desc"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByRole('button', { name: 'Delete' })).toHaveFocus();
  });

  test('custom labels override the defaults', () => {
    render(
      <ConfirmDialog
        title="Sure?"
        description="desc"
        confirmLabel="Do it"
        cancelLabel="Nope"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByRole('button', { name: 'Do it' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Nope' })).toBeVisible();
  });
});

describe('Toggle', () => {
  test('click reports through onChange', () => {
    const onChange = vi.fn();
    render(<Toggle checked={false} onChange={onChange} aria-label="Enable" />);
    fireEvent.click(screen.getByRole('switch', { name: 'Enable' }));
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  test('reflects the checked state via aria', () => {
    render(<Toggle checked onChange={vi.fn()} aria-label="Enable" />);
    expect(screen.getByRole('switch', { name: 'Enable' })).toHaveAttribute(
      'aria-checked',
      'true',
    );
  });

  test('keyboard activation works with Space and Enter', () => {
    const onChange = vi.fn();
    render(<Toggle checked={false} onChange={onChange} aria-label="Enable" />);
    const toggle = screen.getByRole('switch', { name: 'Enable' });
    fireEvent.keyDown(toggle, { key: ' ' });
    fireEvent.keyDown(toggle, { key: 'Enter' });
    expect(onChange).toHaveBeenCalledTimes(2);
  });
});

describe('BatchActionBar', () => {
  const baseProps = {
    totalCount: 4,
    selectedCount: 0,
    allSelected: false,
    onToggleSelectAll: vi.fn(),
    onActivateSelected: vi.fn(),
    onDeactivateSelected: vi.fn(),
    onClearSelection: vi.fn(),
    itemsLabel: 'skills',
  };

  test('shows the count and a disabled select-all when empty', () => {
    render(<BatchActionBar {...baseProps} totalCount={0} />);
    expect(screen.getByText('0 skills')).toBeVisible();
    expect(screen.getByLabelText('Select all skills')).toBeDisabled();
  });

  test('selection reveals the batch actions', () => {
    const onActivateSelected = vi.fn();
    const onDeactivateSelected = vi.fn();
    const onClearSelection = vi.fn();
    render(
      <BatchActionBar
        {...baseProps}
        selectedCount={2}
        onActivateSelected={onActivateSelected}
        onDeactivateSelected={onDeactivateSelected}
        onClearSelection={onClearSelection}
      />,
    );
    expect(screen.getByText('2 selected')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Activate' }));
    expect(onActivateSelected).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: 'Deactivate' }));
    expect(onDeactivateSelected).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: 'Clear' }));
    expect(onClearSelection).toHaveBeenCalledTimes(1);
  });

  test('select-all toggles through the checkbox', () => {
    const onToggleSelectAll = vi.fn();
    render(<BatchActionBar {...baseProps} onToggleSelectAll={onToggleSelectAll} />);
    fireEvent.click(screen.getByLabelText('Select all skills'));
    expect(onToggleSelectAll).toHaveBeenCalledTimes(1);
  });
});
