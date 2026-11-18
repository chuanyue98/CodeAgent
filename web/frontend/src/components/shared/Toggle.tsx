import React, { useEffect, useRef } from 'react';

interface ToggleProps {
  checked: boolean;
  onChange: (e: React.MouseEvent | React.KeyboardEvent) => void;
  'aria-label': string;
  size?: 'sm' | 'md';
  disabled?: boolean;
  className?: string;
}

const sizeClasses = {
  sm: {
    button: 'h-5 w-9',
    knob: 'h-3 w-3',
    on: 'translate-x-5',
    off: 'translate-x-1',
  },
  md: {
    button: 'h-6 w-11',
    knob: 'h-4 w-4',
    on: 'translate-x-6',
    off: 'translate-x-1',
  },
} as const;

/**
 * Accessible toggle switch with proper ARIA semantics (`role="switch"` and `aria-checked`).
 * Supports keyboard activation via Space and Enter without bubbling into parent card actions.
 */
const Toggle: React.FC<ToggleProps> = ({
  checked,
  onChange,
  'aria-label': ariaLabel,
  size = 'sm',
  disabled = false,
  className = '',
}) => {
  const cls = sizeClasses[size];
  const suppressSpaceClickRef = useRef(false);
  const clearSuppressTimerRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (clearSuppressTimerRef.current !== null) {
        window.clearTimeout(clearSuppressTimerRef.current);
      }
    };
  }, []);

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (suppressSpaceClickRef.current) {
      suppressSpaceClickRef.current = false;
      if (clearSuppressTimerRef.current !== null) {
        window.clearTimeout(clearSuppressTimerRef.current);
        clearSuppressTimerRef.current = null;
      }
      return;
    }
    if (disabled) return;
    onChange(e);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === ' ' || e.key === 'Enter') {
      e.preventDefault();
      e.stopPropagation();
      if (disabled) return;
      onChange(e);
    }
  };

  const handleKeyUp = (e: React.KeyboardEvent) => {
    if (e.key === ' ') {
      // Chromium fires a synthetic click on Space keyup after keydown preventDefault();
      // suppress that duplicate activation while letting mouse/test clicks work normally.
      suppressSpaceClickRef.current = true;
      if (clearSuppressTimerRef.current !== null) {
        window.clearTimeout(clearSuppressTimerRef.current);
      }
      clearSuppressTimerRef.current = window.setTimeout(() => {
        suppressSpaceClickRef.current = false;
        clearSuppressTimerRef.current = null;
      }, 0);
    }
  };

  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      disabled={disabled}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      onKeyUp={handleKeyUp}
      className={`relative inline-flex shrink-0 items-center rounded-full transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:ring-offset-1 ${
        disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'
      } ${cls.button} ${checked ? 'bg-primary' : 'bg-muted'} ${className}`}
    >
      <span
        aria-hidden="true"
        className={`inline-block transform rounded-full bg-white transition-transform ${cls.knob} ${
          checked ? cls.on : cls.off
        }`}
      />
    </button>
  );
};

export default Toggle;
