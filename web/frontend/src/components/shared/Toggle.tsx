import React from 'react';

interface ToggleProps {
  checked: boolean;
  onChange: (e: React.MouseEvent | React.KeyboardEvent) => void;
  'aria-label': string;
  size?: 'sm' | 'md';
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
};

/**
 * Accessible toggle switch with proper ARIA semantics.
 * Supports keyboard activation via Space and Enter.
 */
const Toggle: React.FC<ToggleProps> = ({ checked, onChange, 'aria-label': ariaLabel, size = 'sm' }) => {
  const cls = sizeClasses[size];

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === ' ' || e.key === 'Enter') {
      e.preventDefault();
      onChange(e);
    }
  };

  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      onClick={onChange}
      onKeyDown={handleKeyDown}
      className={`relative inline-flex items-center rounded-full transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:ring-offset-1 ${cls.button} ${
        checked ? 'bg-primary' : 'bg-slate-200'
      }`}
    >
      <span
        className={`inline-block transform rounded-full bg-white transition-transform ${cls.knob} ${
          checked ? cls.on : cls.off
        }`}
      />
    </button>
  );
};

export default Toggle;
