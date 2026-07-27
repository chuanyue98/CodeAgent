import type { ReactNode } from 'react';

interface ModalProps {
  children: ReactNode;
  onClose: () => void;
  /** Accessible name. Use `ariaLabelledBy` instead when the panel already renders a visible heading. */
  ariaLabel?: string;
  /** Id of an element inside `children` to use as the accessible name instead of `ariaLabel`. */
  ariaLabelledBy?: string;
  /** Id of an element inside `children` to use as the accessible description. */
  ariaDescribedBy?: string;
  role?: 'dialog' | 'alertdialog';
  /** Classes for the outer backdrop -- vertical position, scroll behavior. */
  overlayClassName?: string;
  /** Classes for the inner glass-card panel -- width, padding, spacing. */
  panelClassName?: string;
  testId?: string;
}

/**
 * Shared overlay + glass-card chrome for modals and dialogs. Every caller
 * previously reimplemented the same backdrop/click-outside/Escape-to-close
 * shell independently (NewTaskModal, GenerateTaskModal, ConfirmDialog,
 * CommandPalette) -- the same duplication the app already fixed once for
 * Gallery components. Content-specific layout stays with the caller via
 * `panelClassName` and children.
 */
export default function Modal({
  children,
  onClose,
  ariaLabel,
  ariaLabelledBy,
  ariaDescribedBy,
  role = 'dialog',
  overlayClassName = 'pt-[10vh] overflow-y-auto',
  panelClassName = 'max-w-xl p-6 space-y-4 mb-[10vh]',
  testId,
}: ModalProps) {
  return (
    <div
      className={`fixed inset-0 z-50 flex items-start justify-center bg-slate-900/40 ${overlayClassName}`}
      role="presentation"
      onClick={onClose}
      onKeyDown={event => {
        if (event.key === 'Escape') onClose();
      }}
    >
      <div
        role={role}
        aria-modal="true"
        aria-label={ariaLabelledBy ? undefined : ariaLabel}
        aria-labelledby={ariaLabelledBy}
        aria-describedby={ariaDescribedBy}
        data-testid={testId}
        className={`glass-card w-full ${panelClassName}`}
        onClick={event => event.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}
