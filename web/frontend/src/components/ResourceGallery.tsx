import { useState, useEffect, useMemo, type ReactNode } from 'react';
import { Search, BookOpen, Layers, Terminal, Globe, Cpu, ChevronRight, type LucideIcon } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { useProject, type GroupDefinition } from '../context/ProjectContext';
import { useT, type Translate } from '../i18n/context';
import type { TranslationKey } from '../i18n/locales/en';
import Toggle from './shared/Toggle';
import ErrorState from './shared/ErrorState';
import LoadingState from './shared/LoadingState';
import useResourceData from '../hooks/useResourceData';
import useResourceToggle from '../hooks/useResourceToggle';
import Toast from './shared/Toast';
import BatchActionBar from './shared/BatchActionBar';

/**
 * A single resource entry (skill, plugin, hook, prompt) shown in a gallery.
 * All resource kinds share this shape, plus an optional `meta` bag for
 * whatever extra fields a given kind wants surfaced via `renderMeta` (a
 * hook's event/path/status, a prompt group's file list, ...) — that's what
 * lets Prompts and Hooks reuse this exact component instead of hand-rolling
 * their own gallery.
 */
export interface ResourceItem<M = unknown> {
  name: string;
  id: string;
  description: string;
  readme: string;
  meta?: M;
}

/**
 * Categorized resource data returned by the resource list endpoints
 * (`/api/skills`, `/api/plugins`, ...): a map of category name -> items.
 */
export type ResourceData<M = unknown> = Record<string, ResourceItem<M>[]>;

/**
 * Labels that differ between resource kinds. Keeping them in a single object
 * lets the thin wrapper components stay declarative and diff-free.
 */
export interface ResourceGalleryLabels {
  /** Sidebar heading, e.g. "Library" / "Registry" */
  sidebar: TranslationKey;
  /** Detail-view eyebrow heading, e.g. "Skill Detail" / "Plugin Detail" */
  detailHeading: TranslationKey;
  /** aria-label for the back button, e.g. "Back to skill list" */
  backLabel: TranslationKey;
  /** sr-only label for the search input, e.g. "Search skills" */
  searchLabel: TranslationKey;
  /** Placeholder text for the search input, e.g. "Search skills..." */
  searchPlaceholder: TranslationKey;
  /** id used for the search input + its sr-only label (not user-visible) */
  searchId: string;
  /** Empty-state message when a category has no matching items */
  emptyCategory: TranslationKey;
  /** Optional empty-state shown in the sidebar when there is no data at all */
  emptySidebar?: TranslationKey;
  /** Singular noun used in activate/deactivate aria-labels */
  itemSingular: TranslationKey;
  /** Plural noun used in the batch bar's count and select-all label */
  itemPlural: TranslationKey;
}

export interface ResourceGalleryProps<M = unknown> {
  /** Which resource list this gallery manages within a group */
  resourceType: keyof GroupDefinition;
  /** API endpoint backing the gallery */
  apiEndpoint: string;
  /**
   * The API endpoints for skills/plugins already return categorized data
   * (category -> items) that matches {@link ResourceData} directly. Hooks
   * and prompts return a flat list instead, so their wrappers pass this to
   * reshape the raw response before it reaches the rest of the component —
   * everything past this point stays kind-agnostic either way.
   */
  transformData?: (raw: unknown, t: Translate) => ResourceData<M>;
  /** Icon rendered on each resource card */
  itemIcon: LucideIcon;
  /** UI labels that differ between resource kinds */
  labels: ResourceGalleryLabels;
  /**
   * Optional kind-specific metadata, rendered both under the card
   * description and under the detail-view header (e.g. a hook's
   * event/path/status, a prompt group's file-count and tags).
   */
  renderMeta?: (item: ResourceItem<M>, t: Translate) => ReactNode;
  /**
   * Optional secondary panel alongside the detail view's markdown body
   * (e.g. a prompt group's "Files in Group" list). When omitted the detail
   * view is a single column.
   */
  renderDetailAside?: (item: ResourceItem<M>, t: Translate) => ReactNode;
  /**
   * Optional extra text pulled from an item's kind-specific `meta` (e.g. a
   * hook's trigger event) that the search box should also match against,
   * beyond the always-searched name/description.
   */
  getSearchableMeta?: (item: ResourceItem<M>) => string;
}

const getCategoryIcon = (category: string) => {
  switch (category.toLowerCase()) {
    case 'base': return <Cpu className="w-4 h-4" />;
    case 'web': return <Globe className="w-4 h-4" />;
    case 'devops': return <Terminal className="w-4 h-4" />;
    default: return <Layers className="w-4 h-4" />;
  }
};

/**
 * Generic gallery for browsing categorized resources (skills, plugins,
 * hooks, prompts) and toggling their activation in the current resource
 * group. Every resource kind gets the exact same interaction chrome —
 * sidebar categories, search, multi-select + batch activate/deactivate,
 * and a click-through detail view — so switching between the Capabilities
 * sub-tabs doesn't mean relearning a different layout each time.
 *
 * The thin per-kind wrappers (SkillGallery, PluginGallery, HooksGallery,
 * PromptsGallery) only supply differing config via props — labels, icon,
 * and, for kinds whose API returns a flat list instead of category ->
 * items, a `transformData` reshape plus an optional `renderMeta`/
 * `renderDetailAside` for whatever extra fields that kind needs surfaced.
 * All rendering logic lives here.
 */
function ResourceGallery<M = unknown>({
  resourceType,
  apiEndpoint,
  transformData,
  itemIcon: ItemIcon,
  labels,
  renderMeta,
  renderDetailAside,
  getSearchableMeta,
}: ResourceGalleryProps<M>) {
  const { currentGroup, groups } = useProject();
  const t = useT();
  const itemNoun = t(labels.itemSingular);
  const { data: rawData, loading, error, refetch } = useResourceData<unknown>(apiEndpoint);
  const resourceData = useMemo(
    () => (rawData ? (transformData ? transformData(rawData, t) : (rawData as ResourceData<M>)) : null),
    [rawData, transformData, t]
  );
  const { toggleResource, toggleResources, toggleError, dismissToggleError } = useResourceToggle();
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [selectedItem, setSelectedItem] = useState<ResourceItem<M> | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!resourceData) return;
    const categories = Object.keys(resourceData);
    // Reset the selected category when the data changes and the previously
    // selected one no longer exists (e.g. after a workspace switch, backend
    // restart, or category rename). Without this, resourceData[selectedCategory]
    // becomes undefined and .filter() throws, bubbling up to the ErrorBoundary
    // and blanking the page.
    const stillValid = selectedCategory && categories.includes(selectedCategory);
    const next = categories.length === 0 ? null : stillValid ? selectedCategory : categories[0];
    if (next !== selectedCategory) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSelectedCategory(next);
    }
  }, [resourceData, selectedCategory]);

  // Switching categories with a stale selection would let a batch action
  // silently apply to items the user can no longer see.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSelectedIds(new Set());
  }, [selectedCategory]);

  const isItemActive = (itemId: string) =>
    groups[currentGroup]?.[resourceType]?.includes(itemId) ?? false;

  const filteredItems = selectedCategory && resourceData
    ? (resourceData[selectedCategory] ?? []).filter(item => {
        const term = searchTerm.toLowerCase();
        return (
          item.name.toLowerCase().includes(term) ||
          item.description.toLowerCase().includes(term) ||
          (getSearchableMeta?.(item).toLowerCase().includes(term) ?? false)
        );
      })
    : [];

  const toggleItemSelected = (itemId: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(itemId)) next.delete(itemId);
      else next.add(itemId);
      return next;
    });
  };

  const allFilteredSelected = filteredItems.length > 0 && filteredItems.every(item => selectedIds.has(item.id));

  const toggleSelectAllFiltered = () => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (allFilteredSelected) filteredItems.forEach(item => next.delete(item.id));
      else filteredItems.forEach(item => next.add(item.id));
      return next;
    });
  };

  const handleActivateSelected = () => {
    void toggleResources(resourceType, Array.from(selectedIds), true).then(() => setSelectedIds(new Set()));
  };

  const handleDeactivateSelected = () => {
    void toggleResources(resourceType, Array.from(selectedIds), false).then(() => setSelectedIds(new Set()));
  };

  if (loading) {
    return <LoadingState />;
  }

  if (error) {
    return <ErrorState message={error} onRetry={refetch} />;
  }

  return (
    <div className="flex h-full overflow-hidden p-6 gap-6">
      {/* Sidebar Categories */}
      <div className="animate-slide-left stagger-1 w-64 shrink-0 glass-card flex flex-col overflow-hidden">
        <div className="p-6 border-b border-slate-100">
          <h2 className="text-sm font-semibold flex items-center gap-2 uppercase tracking-widest text-slate-400">
            <BookOpen className="w-4 h-4 text-primary" />
            {t(labels.sidebar)}
          </h2>
        </div>
        <div className="custom-scrollbar flex-1 overflow-y-auto p-4 space-y-1">
          {resourceData && Object.keys(resourceData).map((category, i) => (
            <button
              key={category}
              onClick={() => {
                setSelectedCategory(category);
                setSelectedItem(null);
              }}
              className={`animate-fade-rise stagger-${Math.min(i + 2, 7)} w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all ${
                selectedCategory === category
                  ? 'bg-primary/10 text-primary'
                  : 'hover:bg-slate-50 text-slate-500 hover:text-slate-900'
              }`}
            >
              {getCategoryIcon(category)}
              <span className="capitalize">{category}</span>
              <span className={`ml-auto text-[10px] px-2 py-0.5 rounded-full border ${
                selectedCategory === category ? 'border-primary/20 bg-primary/10 text-cyan-800' : 'border-slate-100 bg-slate-50'
              }`}>
                {resourceData[category].length}
              </span>
            </button>
          ))}
          {(!resourceData || Object.keys(resourceData).length === 0) && labels.emptySidebar && (
            <div className="p-4 text-xs text-slate-400 italic">{t(labels.emptySidebar)}</div>
          )}
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {selectedItem ? (
          /* Detail View — re-mounts on selection so the entrance plays each time. */
          <div key={selectedItem.id} className="animate-fade-rise stagger-2 flex-1 glass-card flex flex-col overflow-hidden">
            <div className="p-6 border-b border-slate-200 flex items-center gap-4 bg-white">
              <button
                onClick={() => setSelectedItem(null)}
                aria-label={t(labels.backLabel)}
                className="p-2 hover:bg-slate-100 rounded-xl transition-all border border-slate-200"
              >
                <ChevronRight className="w-5 h-5 rotate-180" />
              </button>
              <div className="flex-1">
                <span className="text-[10px] uppercase tracking-widest text-primary font-bold">{t(labels.detailHeading)}</span>
                <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{selectedItem.name}</h1>
              </div>
              <div className="flex items-center gap-3 px-4 py-2 bg-slate-50 rounded-xl border border-slate-200">
                <span className="text-xs font-semibold text-slate-600">{t('gallery.activeIn', { group: currentGroup })}</span>
                <Toggle
                  checked={isItemActive(selectedItem.id)}
                  onChange={(e) => toggleResource(resourceType, selectedItem.id, e)}
                  aria-label={
                    isItemActive(selectedItem.id)
                      ? t('gallery.deactivate', { item: itemNoun })
                      : t('gallery.activate', { item: itemNoun })
                  }
                />
              </div>
            </div>
            {renderMeta && (
              <div className="px-8 py-4 border-b border-slate-100 bg-slate-50/50">
                {renderMeta(selectedItem, t)}
              </div>
            )}
            <div className={`flex-1 min-h-0 overflow-hidden ${renderDetailAside ? 'grid grid-cols-1 lg:grid-cols-[280px_1fr]' : 'flex flex-col'}`}>
              {renderDetailAside && (
                <div className="border-r border-slate-200 bg-slate-50 p-6 overflow-y-auto">
                  {renderDetailAside(selectedItem, t)}
                </div>
              )}
              <div className="flex-1 overflow-y-auto p-8 bg-white prose prose-slate max-w-none prose-headings:text-slate-900 prose-p:text-slate-700 prose-li:text-slate-700 prose-strong:text-slate-900">
                <ReactMarkdown
                  components={{
                    code({className, children, ...props}) {
                      const isCodeBlock = className && className.startsWith('language-');
                      return isCodeBlock ? (
                        <code className={`${className} font-mono`} {...props}>
                          {children}
                        </code>
                      ) : (
                        <code className="font-mono bg-slate-100 border border-slate-200 px-1.5 py-0.5 rounded text-cyan-700 text-[0.875em]" {...props}>
                          {children}
                        </code>
                      );
                    },
                    pre({children, ...props}) {
                      return (
                        <pre className="!bg-slate-900 !text-slate-100 p-5 rounded-xl shadow-inner border border-slate-700 overflow-x-auto" {...props}>
                          {children}
                        </pre>
                      )
                    }
                  }}
                >
                  {selectedItem.readme}
                </ReactMarkdown>
              </div>
            </div>
          </div>
        ) : (
          /* List View */
          <div className="flex-1 flex flex-col overflow-hidden gap-4">
            {/* A search box does not need a full card of its own -- that card
                cost ~100px of vertical space above the fold on every visit. */}
            <div className="animate-fade-rise stagger-2 flex flex-wrap items-center justify-between gap-3">
              <div className="relative w-full max-w-md">
                <label htmlFor={labels.searchId} className="sr-only">{t(labels.searchLabel)}</label>
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  id={labels.searchId}
                  type="text"
                  placeholder={t(labels.searchPlaceholder)}
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full pl-10 pr-4 py-2.5 bg-white border border-slate-200 rounded-xl focus:outline-none focus:ring-1 focus:ring-primary/20 focus:border-primary/30 transition-all text-sm placeholder:text-slate-400"
                />
              </div>
              {/* Split around the group name rather than interpolated into one
                  string: the name is styled, so it has to stay its own node.
                  Both halves are separate keys so each language can put the
                  name where its grammar wants it. */}
              <p className="text-xs text-slate-400">
                {t('gallery.mountHintPrefix', { item: itemNoun })}{' '}
                <span className="font-semibold text-slate-500">{currentGroup}</span>{' '}
                {t('gallery.mountHintSuffix')}
              </p>
            </div>
            <BatchActionBar
              totalCount={filteredItems.length}
              selectedCount={selectedIds.size}
              allSelected={allFilteredSelected}
              onToggleSelectAll={toggleSelectAllFiltered}
              onActivateSelected={handleActivateSelected}
              onDeactivateSelected={handleDeactivateSelected}
              onClearSelection={() => setSelectedIds(new Set())}
              itemsLabel={t(labels.itemPlural)}
            />
            <div className="custom-scrollbar flex-1 overflow-y-auto pr-2">
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {filteredItems.map((item, i) => (
                  <div
                    key={item.id}
                    role="button"
                    tabIndex={0}
                    onClick={() => setSelectedItem(item)}
                    onKeyDown={keyboardEvent => {
                      if (keyboardEvent.key === 'Enter' || keyboardEvent.key === ' ') {
                        keyboardEvent.preventDefault();
                        setSelectedItem(item);
                      }
                    }}
                    // Cap at 6 — long galleries shouldn't cascade forever.
                    className={`animate-fade-rise stagger-${Math.min(i + 3, 7)} group glass-card p-6 hover:border-primary/20 hover:bg-slate-50/50 transition-all cursor-pointer relative overflow-hidden ${
                      !isItemActive(item.id) ? 'bg-slate-50/60 border-slate-200' : ''
                    }`}
                  >
                    <div className="flex justify-between items-start mb-4">
                      <div className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          aria-label={t('gallery.select', { name: item.name })}
                          checked={selectedIds.has(item.id)}
                          onClick={e => e.stopPropagation()}
                          onChange={() => toggleItemSelected(item.id)}
                          className="h-3.5 w-3.5 rounded border-slate-300 text-primary focus:ring-primary"
                        />
                        <div className={`p-2 rounded-lg ${isItemActive(item.id) ? 'bg-primary/10 text-primary' : 'bg-slate-100 text-slate-400'}`}>
                          <ItemIcon className="w-5 h-5" />
                        </div>
                      </div>

                      <Toggle
                        checked={isItemActive(item.id)}
                        onChange={(e) => toggleResource(resourceType, item.id, e)}
                        aria-label={t('gallery.toggleActive', { name: item.name })}
                      />
                    </div>

                    <h2 className="break-words text-lg font-semibold tracking-tight group-hover:text-primary transition-colors mb-2">
                      {item.name}
                    </h2>
                    <p className="text-sm text-slate-500 line-clamp-3 font-medium leading-relaxed">
                      {item.description}
                    </p>
                    {renderMeta && <div className="mt-4">{renderMeta(item, t)}</div>}
                    <div className="mt-6 flex items-center text-[11px] font-semibold uppercase tracking-wider text-primary/60 group-hover:text-primary transition-all group-hover:translate-x-1">
                      {t('gallery.viewDetails')} <ChevronRight className="w-3 h-3 ml-1" />
                    </div>

                    <div className={`absolute top-0 right-0 w-1 h-full transition-all ${
                      isItemActive(item.id) ? 'bg-primary' : 'bg-slate-200'
                    }`} />
                  </div>
                ))}
              </div>
              {filteredItems.length === 0 && (
                <div className="text-center py-20 text-slate-400 glass-card">
                  {t(labels.emptyCategory)}
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

export default ResourceGallery;
