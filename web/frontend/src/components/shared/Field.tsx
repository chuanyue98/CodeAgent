import {
  forwardRef,
  useId,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from 'react';
import { Search } from 'lucide-react';

/**
 * One control chrome for every text entry. The app previously ran two focus
 * camps (ring vs border-only) and four search paddings; both are settled
 * here: focus gives two signals (border warms + soft ring), and the search
 * icon geometry is fixed at left-3 / pl-9 / w-3.5.
 */
const CONTROL =
  'w-full rounded-lg border border-input bg-card px-3 py-2 text-sm text-foreground ' +
  'placeholder:text-muted-foreground/70 transition-colors ' +
  'focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 ' +
  'disabled:cursor-not-allowed disabled:bg-muted disabled:opacity-60';

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className = '', ...rest }, ref) {
    return <input ref={ref} {...rest} className={`${CONTROL} ${className}`} />;
  },
);

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function Textarea({ className = '', ...rest }, ref) {
    return <textarea ref={ref} {...rest} className={`${CONTROL} ${className}`} />;
  },
);

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(
  function Select({ className = '', ...rest }, ref) {
    return <select ref={ref} {...rest} className={`${CONTROL} ${className}`} />;
  },
);

export function SearchInput({ className = '', ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div className="relative">
      <Search
        className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground/70"
        aria-hidden
      />
      <input {...rest} className={`${CONTROL} pl-9 ${className}`} />
    </div>
  );
}

interface FieldProps {
  label?: ReactNode;
  /** Id of the control the label names; omit only when the control is
      aria-labelled some other way. */
  htmlFor?: string;
  hint?: ReactNode;
  error?: ReactNode;
  children: ReactNode;
  className?: string;
}

/** Label + control + hint/error stack. The `error` line renders in the
    destructive token; hint and error can coexist (error wins visually). */
export function Field({ label, htmlFor, hint, error, children, className = '' }: FieldProps) {
  const hintId = useId();
  return (
    <div className={`space-y-1.5 ${className}`}>
      {label && (
        <label htmlFor={htmlFor} className="block text-xs font-medium text-foreground">
          {label}
        </label>
      )}
      {children}
      {error ? (
        <p id={hintId} className="text-xs text-destructive">{error}</p>
      ) : hint ? (
        <p id={hintId} className="text-xs text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  );
}
