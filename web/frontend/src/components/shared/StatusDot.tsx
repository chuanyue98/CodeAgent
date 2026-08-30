type Tone = 'running' | 'success' | 'busy' | 'pending' | 'failed' | 'neutral';

/** Shared with InstancesPage's former STATUS_DOT map so live/healthy hues
    stay consistent everywhere a dot appears. */
const TONE: Record<Tone, string> = {
  running: 'bg-emerald-500',
  success: 'bg-emerald-500',
  busy: 'bg-blue-500',
  pending: 'bg-amber-400',
  failed: 'bg-red-500',
  neutral: 'bg-muted-foreground/40',
};

interface StatusDotProps {
  tone: Tone;
  /** Soft halo for live things (ready/busy/running). Also the only
      sanctioned use of a pulsing dot — `animate-pulse` stays reserved for
      skeletons so "loading" and "alive" never blur together. */
  pulse?: boolean;
  className?: string;
}

export default function StatusDot({ tone, pulse = false, className = '' }: StatusDotProps) {
  return (
    <span className={`relative inline-flex h-2 w-2 shrink-0 ${className}`}>
      {pulse && (
        <span className={`animate-pulse-ring absolute inline-flex h-full w-full rounded-full opacity-60 ${TONE[tone]}`} />
      )}
      <span className={`relative inline-flex h-2 w-2 rounded-full ${TONE[tone]}`} />
    </span>
  );
}
