import type { ButtonHTMLAttributes } from 'react';
import { Loader2, type LucideIcon } from 'lucide-react';
import { buttonClass, type ButtonVariant, type ButtonSize } from './buttonClass';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Shows a spinner and disables the button — use for in-flight actions. */
  loading?: boolean;
  /** Leading icon; ignored while `loading`. */
  icon?: LucideIcon;
}

/**
 * The one button. Every page previously hand-rolled its own (two competing
 * radius/weight camps, four hover idioms); this component is where those
 * decisions now live.
 *
 * `type` is left to the caller — inside `<form>`s the native submit default
 * is relied upon and must not be silently overridden.
 */
export default function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  icon: Icon,
  className = '',
  children,
  disabled,
  ...rest
}: ButtonProps) {
  const iconSize = size === 'sm' ? 'h-3.5 w-3.5' : 'h-4 w-4';
  const isInert = disabled || loading;
  return (
    <button
      {...rest}
      disabled={isInert}
      className={buttonClass(variant, size, className)}
    >
      {loading
        ? <Loader2 className={`animate-spin ${iconSize}`} aria-hidden />
        : Icon
          ? <Icon className={iconSize} aria-hidden />
          : null}
      {children}
    </button>
  );
}
