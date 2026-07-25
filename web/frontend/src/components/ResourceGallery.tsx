import { useState, useEffect } from 'react';
import { Search, BookOpen, Layers, Terminal, Globe, Cpu, ChevronRight, type LucideIcon } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { useProject, type GroupDefinition } from '../context/ProjectContext';
import Toggle from './shared/Toggle';
import ErrorState from './shared/ErrorState';
import LoadingState from './shared/LoadingState';
import useResourceData from '../hooks/useResourceData';
import useResourceToggle from '../hooks/useResourceToggle';
import Toast from './shared/Toast';

/**
 * A single resource entry (skill, plugin, hook, prompt) shown in a gallery.
 * All resource kinds share this exact shape, so the gallery can be generic.
 */
export interface ResourceItem {
  name: string;
  id: string;
  description: string;
  readme: string;
}

/**
 * Categorized resource data returned by the resource list endpoints
 * (`/api/skills`, `/api/plugins`, ...): a map of category name -> items.
 */
export type ResourceData = Record<string, ResourceItem[]>;

/**
 * Labels that differ between resource kinds. Keeping them in a single object
 * lets the thin wrapper components stay declarative and diff-free.
 */
export interface ResourceGalleryLabels {
  /** Sidebar heading, e.g. "Library" / "Registry" */
  sidebar: string;
  /** Detail-view eyebrow heading, e.g. "Skill Detail" / "Plugin Detail" */
  detailHeading: string;
  /** aria-label for the back button, e.g. "Back to skill list" */
  backLabel: string;
  /** sr-only label for the search input, e.g. "Search skills" */
  searchLabel: string;
  /** Placeholder text for the search input, e.g. "Search skills..." */
  searchPlaceholder: string;
  /** id used for the search input + its sr-only label */
  searchId: string;
  /** Empty-state message when a category has no matching items */
  emptyCategory: string;
  /** Optional empty-state shown in the sidebar when there is no data at all */
  emptySidebar?: string;
  /** Lowercase singular noun used in activate/deactivate aria-labels */
  itemSingular: string;
}

export interface ResourceGalleryProps {
  /** Which resource list this gallery manages within a group */
  resourceType: keyof GroupDefinition;
  /** API endpoint returning the categorized resource data */
  apiEndpoint: string;
  /** Icon rendered on each resource card */
  itemIcon: LucideIcon;
  /** UI labels that differ between resource kinds */
  labels: ResourceGalleryLabels;
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
 * Generic gallery for browsing categorized resources (skills, plugins, ...)
 * and toggling their activation in the current resource group.
 *
 * SkillGallery and PluginGallery are thin wrappers that only supply the
 * differing config via props; all rendering logic lives here.
 */
function ResourceGallery({
  resourceType,
  apiEndpoint,
  itemIcon: ItemIcon,
  labels,
}: ResourceGalleryProps) {
  const { currentGroup, groups } = useProject();
  const { data: resourceData, loading, error, refetch } = useResourceData<ResourceData>(apiEndpoint);
  const { toggleResource, toggleError, dismissToggleError } = useResourceToggle();
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [selectedItem, setSelectedItem] = useState<ResourceItem | null>(null);
  const [searchTerm, setSearchTerm] = useState('');

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

  const isItemActive = (itemId: string) =>
    groups[currentGroup]?.[resourceType]?.includes(itemId) ?? false;

  const filteredItems = selectedCategory && resourceData
    ? (resourceData[selectedCategory] ?? []).filter(item =>
        item.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        item.description.toLowerCase().includes(searchTerm.toLowerCase())
      )
    : [];

  if (loading) {
    return <LoadingState />;
  }

  if (error) {
    return <ErrorState message={error} onRetry={refetch} />;
  }

  return (
    <div className="flex h-full overflow-hidden p-6 gap-6">
      {/* Sidebar Categories */}
      <div className="w-64 shrink-0 glass-card flex flex-col overflow-hidden">
        <div className="p-6 border-b border-slate-100">
          <h2 className="text-sm font-semibold flex items-center gap-2 uppercase tracking-widest text-slate-400">
            <BookOpen className="w-4 h-4 text-primary" />
            {labels.sidebar}
          </h2>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-1">
          {resourceData && Object.keys(resourceData).map(category => (
            <button
              key={category}
              onClick={() => {
                setSelectedCategory(category);
                setSelectedItem(null);
              }}
              className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all ${
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
            <div className="p-4 text-xs text-slate-400 italic">{labels.emptySidebar}</div>
          )}
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {selectedItem ? (
          /* Detail View */
          <div className="flex-1 glass-card flex flex-col overflow-hidden">
            <div className="p-6 border-b border-slate-200 flex items-center gap-4 bg-white">
              <button
                onClick={() => setSelectedItem(null)}
                aria-label={labels.backLabel}
                className="p-2 hover:bg-slate-100 rounded-xl transition-all border border-slate-200"
              >
                <ChevronRight className="w-5 h-5 rotate-180" />
              </button>
              <div className="flex-1">
                <span className="text-[10px] uppercase tracking-widest text-primary font-bold">{labels.detailHeading}</span>
                <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{selectedItem.name}</h1>
              </div>
              <div className="flex items-center gap-3 px-4 py-2 bg-slate-50 rounded-xl border border-slate-200">
                <span className="text-xs font-semibold text-slate-600">Active in {currentGroup}</span>
                <Toggle
                  checked={isItemActive(selectedItem.id)}
                  onChange={(e) => toggleResource(resourceType, selectedItem.id, e)}
                  aria-label={isItemActive(selectedItem.id) ? `Deactivate ${labels.itemSingular}` : `Activate ${labels.itemSingular}`}
                />
              </div>
            </div>
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
        ) : (
          /* List View */
          <div className="flex-1 flex flex-col overflow-hidden gap-4">
            {/* A search box does not need a full card of its own -- that card
                cost ~100px of vertical space above the fold on every visit. */}
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="relative w-full max-w-md">
                <label htmlFor={labels.searchId} className="sr-only">{labels.searchLabel}</label>
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  id={labels.searchId}
                  type="text"
                  placeholder={labels.searchPlaceholder}
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full pl-10 pr-4 py-2.5 bg-white border border-slate-200 rounded-xl focus:outline-none focus:ring-1 focus:ring-primary/20 focus:border-primary/30 transition-all text-sm placeholder:text-slate-400"
                />
              </div>
              <p className="text-xs text-slate-400">
                Toggle a {labels.itemSingular} to mount it for the <span className="font-semibold text-slate-500">{currentGroup}</span> group
              </p>
            </div>
            <div className="flex-1 overflow-y-auto pr-2">
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {filteredItems.map(item => (
                  <div
                    key={item.id}
                    onClick={() => setSelectedItem(item)}
                    className={`group glass-card p-6 hover:border-primary/20 hover:bg-slate-50/50 transition-all cursor-pointer relative overflow-hidden ${
                      !isItemActive(item.id) ? 'bg-slate-50/60 border-slate-200' : ''
                    }`}
                  >
                    <div className="flex justify-between items-start mb-4">
                      <div className={`p-2 rounded-lg ${isItemActive(item.id) ? 'bg-primary/10 text-primary' : 'bg-slate-100 text-slate-400'}`}>
                        <ItemIcon className="w-5 h-5" />
                      </div>

                      <Toggle
                        checked={isItemActive(item.id)}
                        onChange={(e) => toggleResource(resourceType, item.id, e)}
                        aria-label={`Toggle ${item.name} active status`}
                      />
                    </div>

                    <h2 className="break-words text-lg font-semibold tracking-tight group-hover:text-primary transition-colors mb-2">
                      {item.name}
                    </h2>
                    <p className="text-sm text-slate-500 line-clamp-3 font-medium leading-relaxed">
                      {item.description}
                    </p>
                    <div className="mt-6 flex items-center text-[11px] font-semibold uppercase tracking-wider text-primary/60 group-hover:text-primary transition-all group-hover:translate-x-1">
                      View details <ChevronRight className="w-3 h-3 ml-1" />
                    </div>

                    <div className={`absolute top-0 right-0 w-1 h-full transition-all ${
                      isItemActive(item.id) ? 'bg-primary' : 'bg-slate-200'
                    }`} />
                  </div>
                ))}
              </div>
              {filteredItems.length === 0 && (
                <div className="text-center py-20 text-slate-400 glass-card">
                  {labels.emptyCategory}
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
