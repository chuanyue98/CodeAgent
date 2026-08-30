import type { HTMLAttributes } from 'react';

type Variant = 'default' | 'feature' | 'flat';

const VARIANT_CLASS: Record<Variant, string> = {
  default: 'glass-card',
  feature: 'glass-card-feature',
  flat: 'glass-card-flat',
};

interface GlassCardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: Variant;
  /** Adds the shared hover idiom (border warms toward primary). Use only on
      cards whose whole surface is a click target. */
  interactive?: boolean;
}

/**
 * The one card container. Selection rule:
 * - `default` — regular content cards.
 * - `feature` — hero/feature tiles; stronger elevation, larger radius.
 * - `flat` — cards holding hundreds of scrolling rows. backdrop-filter
 *   re-computes the blurred backdrop every frame something above it moves,
 *   so long lists pay for blur continuously (see index.css).
 * Wrapping a bare `glass-card` class string keeps tests that assert on the
 * class name passing; prefer the component so the rule stays enforceable.
 */
export default function GlassCard({
  variant = 'default',
  interactive = false,
  className = '',
  children,
  ...rest
}: GlassCardProps) {
  return (
    <div
      {...rest}
      className={`${VARIANT_CLASS[variant]}${interactive ? ' glass-card-interactive' : ''} ${className}`}
    >
      {children}
    </div>
  );
}
