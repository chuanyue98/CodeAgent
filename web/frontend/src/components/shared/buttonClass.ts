/**
 * The Button idiom as a class string, for elements that can't be a <button>
 * (Link, router NavLink). Lives apart from Button.tsx so that file exports
 * only its component (react-refresh/only-export-components).
 */

export type ButtonVariant = 'primary' | 'soft' | 'outline' | 'ghost' | 'destructive';
export type ButtonSize = 'sm' | 'md' | 'lg';

const VARIANTS: Record<ButtonVariant, string> = {
  primary: 'bg-primary text-primary-foreground transition-all hover:bg-primary/90 active:scale-95',
  soft: 'bg-primary/10 text-primary transition-colors hover:bg-primary/15',
  outline: 'border border-border text-foreground transition-colors hover:bg-muted/60',
  ghost: 'text-muted-foreground transition-colors hover:bg-muted hover:text-foreground',
  destructive: 'border border-destructive/30 text-destructive transition-colors hover:bg-destructive/10',
};

const SIZES: Record<ButtonSize, string> = {
  sm: 'px-2.5 py-1.5 text-xs',
  md: 'px-3.5 py-2 text-sm',
  lg: 'px-4 py-2.5 text-sm',
};

const BASE =
  'inline-flex items-center justify-center gap-2 rounded-lg font-medium ' +
  'disabled:pointer-events-none disabled:opacity-50';

export function buttonClass(
  variant: ButtonVariant = 'primary',
  size: ButtonSize = 'md',
  className = '',
) {
  return `${BASE} ${VARIANTS[variant]} ${SIZES[size]} ${className}`;
}
