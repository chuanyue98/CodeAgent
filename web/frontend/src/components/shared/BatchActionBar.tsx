import { useT } from '../../i18n/context';

interface BatchActionBarProps {
  totalCount: number;
  selectedCount: number;
  allSelected: boolean;
  onToggleSelectAll: () => void;
  onActivateSelected: () => void;
  onDeactivateSelected: () => void;
  onClearSelection: () => void;
  /** Plural noun for the items being counted, already translated. */
  itemsLabel: string;
}

/**
 * Select-all + count + activate/deactivate row shared by the resource
 * galleries (skills/plugins/hooks) so switching a resource combo is one
 * request for N items instead of N requests.
 */
export default function BatchActionBar({
  totalCount,
  selectedCount,
  allSelected,
  onToggleSelectAll,
  onActivateSelected,
  onDeactivateSelected,
  onClearSelection,
  itemsLabel,
}: BatchActionBarProps) {
  const t = useT();
  return (
    <div className="flex flex-wrap items-center gap-3 text-xs">
      <label className="flex items-center gap-2 text-slate-500 font-medium cursor-pointer select-none">
        <input
          type="checkbox"
          aria-label={t('batch.selectAll', { items: itemsLabel })}
          checked={allSelected}
          onChange={onToggleSelectAll}
          disabled={totalCount === 0}
          className="h-3.5 w-3.5 rounded border-slate-300 text-primary focus:ring-primary"
        />
        {t('batch.count', { count: totalCount, items: itemsLabel })}
      </label>
      {selectedCount > 0 && (
        <span className="flex items-center gap-2">
          <span className="text-slate-500">{t('batch.selected', { count: selectedCount })}</span>
          <button
            onClick={onActivateSelected}
            className="px-2 py-1 rounded-md border border-primary/20 text-primary hover:bg-primary/5 transition-colors font-medium"
          >
            {t('batch.activate')}
          </button>
          <button
            onClick={onDeactivateSelected}
            className="px-2 py-1 rounded-md border border-slate-200 text-slate-600 hover:bg-slate-50 transition-colors font-medium"
          >
            {t('batch.deactivate')}
          </button>
          <button
            onClick={onClearSelection}
            className="px-2 py-1 rounded-md text-slate-400 hover:text-slate-600 transition-colors"
          >
            {t('common.clear')}
          </button>
        </span>
      )}
    </div>
  );
}
