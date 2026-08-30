import Button from './Button';
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
      <label className="flex items-center gap-2 text-muted-foreground font-medium cursor-pointer select-none">
        <input
          type="checkbox"
          aria-label={t('batch.selectAll', { items: itemsLabel })}
          checked={allSelected}
          onChange={onToggleSelectAll}
          disabled={totalCount === 0}
          className="h-3.5 w-3.5 rounded border-border text-primary focus:ring-primary"
        />
        {t('batch.count', { count: totalCount, items: itemsLabel })}
      </label>
      {selectedCount > 0 && (
        <span className="flex items-center gap-2">
          <span className="text-muted-foreground">{t('batch.selected', { count: selectedCount })}</span>
          <Button variant="soft" size="sm" onClick={onActivateSelected}>
            {t('batch.activate')}
          </Button>
          <Button variant="outline" size="sm" onClick={onDeactivateSelected}>
            {t('batch.deactivate')}
          </Button>
          <Button variant="ghost" size="sm" onClick={onClearSelection}>
            {t('common.clear')}
          </Button>
        </span>
      )}
    </div>
  );
}
