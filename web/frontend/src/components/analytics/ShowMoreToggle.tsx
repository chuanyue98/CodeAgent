import { useT } from '../../i18n/context';

export interface ShowMoreToggleProps {
  expanded: boolean;
  /** Total rows behind the toggle — shown so "show all" says how many. */
  total: number;
  onToggle: () => void;
}

/**
 * The "top N, then the rest on request" control.
 *
 * Three panels on the usage page render an unbounded list, and between them
 * they were most of a 4,800px page. This is the tool ranking's existing
 * treatment, lifted out so the model breakdown and the daily table use the
 * same one rather than each growing their own.
 */
export default function ShowMoreToggle({ expanded, total, onToggle }: ShowMoreToggleProps) {
  const t = useT();
  return (
    <button
      onClick={onToggle}
      className="mt-3 text-xs font-medium text-primary transition-opacity hover:opacity-80"
    >
      {expanded ? t('common.showLess') : t('common.showAll', { count: String(total) })}
    </button>
  );
}
