import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router';
import { BookOpen, ChevronDown, ChevronRight, Cpu, Globe, Layers, Search, Terminal } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { useProject } from '../context/ProjectContext';
import { useT } from '../i18n/context';
import useAllResourceData, { type LoadedKind } from '../hooks/useAllResourceData';
import useResourceToggle from '../hooks/useResourceToggle';
import type { ResourceKindConfig, ResourceKindId } from './resources/resourceKinds';
import type { ResourceItem } from './resources/types';
import BatchActionBar from './shared/BatchActionBar';
import ErrorState from './shared/ErrorState';
import LoadingState from './shared/LoadingState';
import Toast from './shared/Toast';
import Toggle from './shared/Toggle';

interface Selection {
  kindId: ResourceKindId;
  category: string;
}

/** One search hit, carrying the kind it came from. */
interface Hit {
  kind: ResourceKindConfig;
  category: string;
  item: ResourceItem;
}

const categoryIcon = (category: string) => {
  switch (category.toLowerCase()) {
    case 'base': return <Cpu className="h-3.5 w-3.5" />;
    case 'web': return <Globe className="h-3.5 w-3.5" />;
    case 'devops': return <Terminal className="h-3.5 w-3.5" />;
    default: return <Layers className="h-3.5 w-3.5" />;
  }
};

function matches(kind: ResourceKindConfig, item: ResourceItem, term: string): boolean {
  if (!term) return true;
  return (
    item.name.toLowerCase().includes(term) ||
    item.description.toLowerCase().includes(term) ||
    (kind.getSearchableMeta?.(item).toLowerCase().includes(term) ?? false)
  );
}

/**
 * One page for every group-scoped resource, replacing the four sibling tabs
 * that each showed one kind.
 *
 * Two things were wrong with a tab per kind, and neither was the component —
 * all four already shared one gallery. Answering "what is this group actually
 * running?" meant visiting four tabs, and each tab's search box only searched
 * its own kind, so "was that lint thing a skill or a hook?" had no answer at
 * all. Both are properties of the navigation, so the navigation is what
 * changed.
 *
 * MCP deliberately stays its own tab: it is configured per engine rather than
 * per group, so listing it here would put it under a group selector that does
 * not apply to it.
 */
export default function ResourceHub() {
  const t = useT();
  const { currentGroup, groups } = useProject();
  const { kinds, loading, failed, refetchAll } = useAllResourceData();
  const { toggleResource, toggleResources, toggleError, dismissToggleError } = useResourceToggle();
  const [searchParams, setSearchParams] = useSearchParams();

  const [selection, setSelection] = useState<Selection | null>(null);
  const [openItem, setOpenItem] = useState<Hit | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [collapsed, setCollapsed] = useState<Set<ResourceKindId>>(new Set());

  const term = searchTerm.trim().toLowerCase();
  const searching = term.length > 0;

  const byId = useMemo(() => {
    const map = new Map<ResourceKindId, LoadedKind>();
    kinds.forEach(kind => map.set(kind.config.id, kind));
    return map;
  }, [kinds]);

  // The old per-kind routes redirect here carrying ?kind=..., so a bookmark
  // to /settings/hooks still lands on hooks rather than on whatever sorts
  // first.
  const requestedKind = searchParams.get('kind');

  useEffect(() => {
    if (loading) return;
    const stillValid =
      selection && (byId.get(selection.kindId)?.data?.[selection.category]?.length ?? 0) >= 0
      && Boolean(byId.get(selection.kindId)?.data?.[selection.category]);
    if (stillValid) return;

    const preferred = requestedKind
      ? kinds.find(kind => kind.config.id === requestedKind && kind.count > 0)
      : undefined;
    const first = preferred ?? kinds.find(kind => kind.count > 0);
    const category = first ? Object.keys(first.data ?? {})[0] : undefined;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSelection(first && category ? { kindId: first.config.id, category } : null);
  }, [loading, kinds, byId, selection, requestedKind]);

  // A stale selection would let a batch action apply to items that are no
  // longer on screen.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSelectedIds(new Set());
  }, [selection, term]);

  const isActive = (kindId: ResourceKindId, itemId: string) =>
    groups[currentGroup]?.[kindId]?.includes(itemId) ?? false;

  /** Every item of every kind that matches the search, in kind order. */
  const hits = useMemo<Hit[]>(() => {
    if (!searching) return [];
    const found: Hit[] = [];
    for (const kind of kinds) {
      for (const [category, items] of Object.entries(kind.data ?? {})) {
        for (const item of items) {
          if (matches(kind.config, item, term)) {
            found.push({ kind: kind.config, category, item });
          }
        }
      }
    }
    return found;
  }, [kinds, searching, term]);

  const hitCountByKind = useMemo(() => {
    const counts = new Map<ResourceKindId, number>();
    for (const hit of hits) {
      counts.set(hit.kind.id, (counts.get(hit.kind.id) ?? 0) + 1);
    }
    return counts;
  }, [hits]);

  const activeKind = selection ? byId.get(selection.kindId) : undefined;
  const browseItems: Hit[] = useMemo(() => {
    if (searching || !selection || !activeKind?.data) return [];
    return (activeKind.data[selection.category] ?? []).map(item => ({
      kind: activeKind.config,
      category: selection.category,
      item,
    }));
  }, [searching, selection, activeKind]);

  const shown = searching ? hits : browseItems;

  // Batch actions write one kind's list at a time, so they are offered only
  // while browsing a single kind. Across a mixed search result there is no
  // single list to write.
  const batchable = !searching && selection !== null;
  const allSelected = batchable && shown.length > 0 && shown.every(hit => selectedIds.has(hit.item.id));

  const toggleSelectAll = () => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (allSelected) shown.forEach(hit => next.delete(hit.item.id));
      else shown.forEach(hit => next.add(hit.item.id));
      return next;
    });
  };

  const applyBatch = (activate: boolean) => {
    if (!selection) return;
    void toggleResources(selection.kindId, Array.from(selectedIds), activate).then(() =>
      setSelectedIds(new Set()),
    );
  };

  const selectCategory = (kindId: ResourceKindId, category: string) => {
    setSelection({ kindId, category });
    setOpenItem(null);
    setSearchTerm('');
    if (requestedKind && requestedKind !== kindId) {
      const next = new URLSearchParams(searchParams);
      next.delete('kind');
      setSearchParams(next, { replace: true });
    }
  };

  if (loading) return <LoadingState />;

  // Every kind failing means the API is down; that is worth the whole page.
  // One kind failing is not — the other three are still usable, so it gets a
  // banner instead.
  if (failed.length === kinds.length && kinds.length > 0) {
    return <ErrorState message={failed[0].error ?? ''} onRetry={refetchAll} />;
  }

  return (
    <div className="flex h-full gap-6 overflow-hidden p-6">
      {/* ── Sidebar: kind > category ─────────────────────────────────────── */}
      <div className="animate-slide-left stagger-1 glass-card flex w-64 shrink-0 flex-col overflow-hidden">
        <div className="border-b border-slate-100 p-6">
          <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-widest text-slate-400">
            <BookOpen className="h-4 w-4 text-primary" />
            {t('resources.sidebar')}
          </h2>
        </div>
        <div className="custom-scrollbar flex-1 space-y-1 overflow-y-auto p-4">
          {kinds.map(kind => {
            const categories = Object.keys(kind.data ?? {});
            const isCollapsed = collapsed.has(kind.config.id);
            const hitCount = hitCountByKind.get(kind.config.id) ?? 0;
            const KindIcon = kind.config.itemIcon;
            return (
              <div key={kind.config.id}>
                <button
                  onClick={() =>
                    setCollapsed(prev => {
                      const next = new Set(prev);
                      if (next.has(kind.config.id)) next.delete(kind.config.id);
                      else next.add(kind.config.id);
                      return next;
                    })
                  }
                  aria-expanded={!isCollapsed}
                  className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm font-semibold text-slate-600 transition-colors hover:bg-slate-50"
                >
                  {isCollapsed ? (
                    <ChevronRight className="h-3.5 w-3.5 text-slate-300" />
                  ) : (
                    <ChevronDown className="h-3.5 w-3.5 text-slate-300" />
                  )}
                  <KindIcon className="h-4 w-4 text-slate-400" />
                  <span className="flex-1">{t(kind.config.labelKey)}</span>
                  <span
                    className={`rounded-full border px-2 py-0.5 text-[10px] ${
                      searching && hitCount > 0
                        ? 'border-primary/20 bg-primary/10 text-primary'
                        : 'border-slate-100 bg-slate-50 text-slate-500'
                    }`}
                  >
                    {searching ? hitCount : kind.count}
                  </span>
                </button>

                {!isCollapsed && (
                  <div className="ml-4 space-y-0.5 border-l border-slate-100 pl-2">
                    {kind.error && (
                      <p className="px-2 py-1.5 text-[11px] italic text-red-400">
                        {t('resources.kindFailed')}
                      </p>
                    )}
                    {!kind.error && categories.length === 0 && (
                      <p className="px-2 py-1.5 text-[11px] italic text-slate-400">
                        {kind.config.emptyKindKey
                          ? t(kind.config.emptyKindKey)
                          : t('resources.kindEmpty')}
                      </p>
                    )}
                    {categories.map(category => {
                      const selected =
                        !searching &&
                        selection?.kindId === kind.config.id &&
                        selection.category === category;
                      return (
                        <button
                          key={category}
                          onClick={() => selectCategory(kind.config.id, category)}
                          className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-xs font-medium transition-colors ${
                            selected
                              ? 'bg-primary/10 text-primary'
                              : 'text-slate-500 hover:bg-slate-50 hover:text-slate-900'
                          }`}
                        >
                          {categoryIcon(category)}
                          <span className="flex-1 truncate text-left capitalize">{category}</span>
                          <span className="text-[10px] text-slate-400">
                            {(kind.data?.[category] ?? []).length}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Main ─────────────────────────────────────────────────────────── */}
      <div className="flex min-w-0 flex-1 flex-col">
        {openItem ? (
          <DetailView
            hit={openItem}
            active={isActive(openItem.kind.id, openItem.item.id)}
            currentGroup={currentGroup}
            onBack={() => setOpenItem(null)}
            onToggle={event => toggleResource(openItem.kind.id, openItem.item.id, event)}
          />
        ) : (
          <div className="flex min-h-0 flex-1 flex-col gap-4">
            <div className="animate-fade-rise stagger-2 flex flex-wrap items-center justify-between gap-3">
              <div className="relative w-full max-w-md">
                <label htmlFor="resource-search" className="sr-only">
                  {t('resources.searchLabel')}
                </label>
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input
                  id="resource-search"
                  type="text"
                  placeholder={t('resources.searchPlaceholder')}
                  value={searchTerm}
                  onChange={e => setSearchTerm(e.target.value)}
                  className="w-full rounded-xl border border-slate-200 bg-white py-2.5 pl-10 pr-4 text-sm transition-all placeholder:text-slate-400 focus:border-primary/30 focus:outline-none focus:ring-1 focus:ring-primary/20"
                />
              </div>
              <p className="text-xs text-slate-400">
                {t('resources.mountHintPrefix')}{' '}
                <span className="font-semibold text-slate-500">{currentGroup}</span>{' '}
                {t('resources.mountHintSuffix')}
              </p>
            </div>

            {failed.length > 0 && failed.length < kinds.length && (
              <div className="rounded-lg border border-amber-100 bg-amber-50/60 px-3 py-2 text-xs text-amber-700">
                {t('resources.partialFailure', {
                  kinds: failed.map(kind => t(kind.config.labelKey)).join(', '),
                })}
              </div>
            )}

            {searching ? (
              <p className="text-xs text-slate-400">
                {hits.length === 1
                  ? t('resources.searchCountOne', { count: hits.length })
                  : t('resources.searchCount', { count: hits.length })}
              </p>
            ) : (
              <BatchActionBar
                totalCount={shown.length}
                selectedCount={selectedIds.size}
                allSelected={allSelected}
                onToggleSelectAll={toggleSelectAll}
                onActivateSelected={() => applyBatch(true)}
                onDeactivateSelected={() => applyBatch(false)}
                onClearSelection={() => setSelectedIds(new Set())}
                itemsLabel={
                  selection ? t(byId.get(selection.kindId)?.config.itemPluralKey ?? 'noun.skills') : ''
                }
              />
            )}

            <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto pr-2">
              <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
                {shown.map((hit, i) => {
                  const active = isActive(hit.kind.id, hit.item.id);
                  const ItemIcon = hit.kind.itemIcon;
                  return (
                    <div
                      key={`${hit.kind.id}:${hit.item.id}`}
                      role="button"
                      tabIndex={0}
                      onClick={() => setOpenItem(hit)}
                      onKeyDown={event => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault();
                          setOpenItem(hit);
                        }
                      }}
                      className={`animate-fade-rise stagger-${Math.min(i + 3, 7)} group glass-card relative cursor-pointer overflow-hidden p-6 transition-all hover:border-primary/20 hover:bg-slate-50/50 ${
                        !active ? 'border-slate-200 bg-slate-50/60' : ''
                      }`}
                    >
                      <div className="mb-4 flex items-start justify-between">
                        <div className="flex items-center gap-2">
                          {!searching && (
                            <input
                              type="checkbox"
                              aria-label={t('gallery.select', { name: hit.item.name })}
                              checked={selectedIds.has(hit.item.id)}
                              onClick={event => event.stopPropagation()}
                              onChange={() =>
                                setSelectedIds(prev => {
                                  const next = new Set(prev);
                                  if (next.has(hit.item.id)) next.delete(hit.item.id);
                                  else next.add(hit.item.id);
                                  return next;
                                })
                              }
                              className="h-3.5 w-3.5 rounded border-slate-300 text-primary focus:ring-primary"
                            />
                          )}
                          <div className={`rounded-lg p-2 ${active ? 'bg-primary/10 text-primary' : 'bg-slate-100 text-slate-400'}`}>
                            <ItemIcon className="h-5 w-5" />
                          </div>
                        </div>
                        <Toggle
                          checked={active}
                          onChange={event => toggleResource(hit.kind.id, hit.item.id, event)}
                          aria-label={t('gallery.toggleActive', { name: hit.item.name })}
                        />
                      </div>

                      {/* The kind badge is what makes a mixed result list
                          readable — without it a hit is a name with no clue
                          which of the four things it is. */}
                      {searching && (
                        <span className="mb-2 inline-block rounded-full border border-slate-100 bg-slate-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-slate-500">
                          {t(hit.kind.labelKey)}
                        </span>
                      )}

                      <h2 className="mb-2 break-words text-lg font-semibold tracking-tight transition-colors group-hover:text-primary">
                        {hit.item.name}
                      </h2>
                      <p className="line-clamp-3 text-sm font-medium leading-relaxed text-slate-500">
                        {hit.item.description}
                      </p>
                      {hit.kind.renderMeta && (
                        <div className="mt-4">{hit.kind.renderMeta(hit.item, t, active)}</div>
                      )}
                      <div className="mt-6 flex items-center text-[11px] font-semibold uppercase tracking-wider text-primary/60 transition-all group-hover:translate-x-1 group-hover:text-primary">
                        {t('gallery.viewDetails')} <ChevronRight className="ml-1 h-3 w-3" />
                      </div>
                      <div className={`absolute right-0 top-0 h-full w-1 transition-all ${active ? 'bg-primary' : 'bg-slate-200'}`} />
                    </div>
                  );
                })}
              </div>
              {shown.length === 0 && (
                <div className="glass-card py-20 text-center text-slate-400">
                  {searching ? t('resources.noSearchMatch') : t('resources.emptyCategory')}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
      {toggleError && <Toast message={toggleError} onDismiss={dismissToggleError} />}
    </div>
  );
}

interface DetailViewProps {
  hit: Hit;
  active: boolean;
  currentGroup: string;
  onBack: () => void;
  onToggle: (event: React.MouseEvent | React.KeyboardEvent) => void;
}

/** Re-mounts on selection so the entrance animation plays each time. */
function DetailView({ hit, active, currentGroup, onBack, onToggle }: DetailViewProps) {
  const t = useT();
  const { kind, item } = hit;
  const itemNoun = t(kind.itemSingularKey);

  return (
    <div key={item.id} className="animate-fade-rise stagger-2 glass-card flex flex-1 flex-col overflow-hidden">
      <div className="flex items-center gap-4 border-b border-slate-200 bg-white p-6">
        <button
          onClick={onBack}
          aria-label={t('resources.back')}
          className="rounded-xl border border-slate-200 p-2 transition-all hover:bg-slate-100"
        >
          <ChevronRight className="h-5 w-5 rotate-180" />
        </button>
        <div className="flex-1">
          <span className="text-[10px] font-bold uppercase tracking-widest text-primary">
            {t(kind.detailHeadingKey)}
          </span>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{item.name}</h1>
        </div>
        <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-2">
          <span className="text-xs font-semibold text-slate-600">
            {t('gallery.activeIn', { group: currentGroup })}
          </span>
          <Toggle
            checked={active}
            onChange={onToggle}
            aria-label={active ? t('gallery.deactivate', { item: itemNoun }) : t('gallery.activate', { item: itemNoun })}
          />
        </div>
      </div>
      {kind.renderMeta && (
        <div className="border-b border-slate-100 bg-slate-50/50 px-8 py-4">
          {kind.renderMeta(item, t, active)}
        </div>
      )}
      <div className={`min-h-0 flex-1 overflow-hidden ${kind.renderDetailAside ? 'grid grid-cols-1 lg:grid-cols-[280px_1fr]' : 'flex flex-col'}`}>
        {kind.renderDetailAside && (
          <div className="overflow-y-auto border-r border-slate-200 bg-slate-50 p-6">
            {kind.renderDetailAside(item, t)}
          </div>
        )}
        <div className="prose prose-slate max-w-none flex-1 overflow-y-auto bg-white p-8 prose-headings:text-slate-900 prose-p:text-slate-700 prose-strong:text-slate-900 prose-li:text-slate-700">
          <ReactMarkdown
            components={{
              code({ className, children, ...props }) {
                const isCodeBlock = className && className.startsWith('language-');
                return isCodeBlock ? (
                  <code className={`${className} font-mono`} {...props}>
                    {children}
                  </code>
                ) : (
                  <code className="rounded border border-slate-200 bg-slate-100 px-1.5 py-0.5 font-mono text-[0.875em] text-cyan-700" {...props}>
                    {children}
                  </code>
                );
              },
              pre({ children, ...props }) {
                return (
                  <pre className="overflow-x-auto rounded-xl border border-slate-700 !bg-slate-900 p-5 !text-slate-100 shadow-inner" {...props}>
                    {children}
                  </pre>
                );
              },
            }}
          >
            {item.readme}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  );
}
