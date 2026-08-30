import type { ReactNode } from 'react';

interface SectionLabelProps {
  children: ReactNode;
  className?: string;
  /** Element to render. Headings keep their level for document outline;
      labels (`label`) need an `htmlFor` from the caller. */
  as?: 'p' | 'span' | 'h2' | 'h3' | 'h4' | 'label';
}

/** The one eyebrow size. Five coexisting specs (text-[10px] to text-xs,
    semibold to black, tracking-wider to widest) settled here. */
export default function SectionLabel({
  children,
  className = '',
  as: Tag = 'p',
}: SectionLabelProps) {
  return (
    <Tag className={`text-[11px] font-semibold uppercase tracking-wider text-muted-foreground ${className}`}>
      {children}
    </Tag>
  );
}
