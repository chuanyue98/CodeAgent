import React, { useState, useEffect } from 'react';
import { Search, BookOpen, Layers, Terminal, Globe, Cpu, ChevronRight, Zap } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { useProject } from '../context/ProjectContext';
import Toggle from './shared/Toggle';
import ErrorState from './shared/ErrorState';
import LoadingState from './shared/LoadingState';
import useResourceData from '../hooks/useResourceData';
import useResourceToggle from '../hooks/useResourceToggle';

interface Plugin {
  name: string;
  id: string;
  description: string;
  readme: string;
}

interface PluginsData {
  [category: string]: Plugin[];
}

const PluginGallery: React.FC = () => {
  const { currentGroup, groups } = useProject();
  const { data: pluginsData, loading, error, refetch } = useResourceData<PluginsData>('/api/plugins');
  const { toggleResource, toggleError } = useResourceToggle();
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [selectedPlugin, setSelectedPlugin] = useState<Plugin | null>(null);
  const [searchTerm, setSearchTerm] = useState('');

  useEffect(() => {
    if (pluginsData) {
      const categories = Object.keys(pluginsData);
      if (categories.length > 0 && !selectedCategory) {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setSelectedCategory(categories[0]);
      }
    }
  }, [pluginsData, selectedCategory]);

  const isPluginActive = (pluginId: string) => {
    return groups[currentGroup]?.plugins?.includes(pluginId) ?? false;
  };

  const getCategoryIcon = (category: string) => {
    switch (category.toLowerCase()) {
      case 'base': return <Cpu className="w-4 h-4" />;
      case 'web': return <Globe className="w-4 h-4" />;
      case 'devops': return <Terminal className="w-4 h-4" />;
      default: return <Layers className="w-4 h-4" />;
    }
  };

  const filteredPlugins = selectedCategory && pluginsData
    ? pluginsData[selectedCategory].filter(plugin =>
        plugin.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        plugin.description.toLowerCase().includes(searchTerm.toLowerCase())
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
            Registry
          </h2>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-1">
          {pluginsData && Object.keys(pluginsData).map(category => (
            <button
              key={category}
              onClick={() => {
                setSelectedCategory(category);
                setSelectedPlugin(null);
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
                {pluginsData[category].length}
              </span>
            </button>
          ))}
          {(!pluginsData || Object.keys(pluginsData).length === 0) && (
            <div className="p-4 text-xs text-slate-400 italic">No plugins found</div>
          )}
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {selectedPlugin ? (
          /* Plugin Detail View */
          <div className="flex-1 glass-card flex flex-col overflow-hidden">
            <div className="p-6 border-b border-slate-200 flex items-center gap-4 bg-white">
              <button
                onClick={() => setSelectedPlugin(null)}
                aria-label="Back to plugin list"
                className="p-2 hover:bg-slate-100 rounded-xl transition-all border border-slate-200"
              >
                <ChevronRight className="w-5 h-5 rotate-180" />
              </button>
              <div className="flex-1">
                <span className="text-[10px] uppercase tracking-widest text-primary font-bold">Plugin Detail</span>
                <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{selectedPlugin.name}</h1>
              </div>
              <div className="flex items-center gap-3 px-4 py-2 bg-slate-50 rounded-xl border border-slate-200">
                <span className="text-xs font-semibold text-slate-600">Active in {currentGroup}</span>
                <Toggle
                  checked={isPluginActive(selectedPlugin.id)}
                  onChange={(e) => toggleResource('plugins', selectedPlugin.id, e)}
                  aria-label={isPluginActive(selectedPlugin.id) ? 'Deactivate plugin' : 'Activate plugin'}
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
                {selectedPlugin.readme}
              </ReactMarkdown>
            </div>
          </div>
        ) : (
          /* Plugin List View */
          <div className="flex-1 flex flex-col overflow-hidden gap-6">
            <div className="p-6 glass-card bg-slate-50/30 backdrop-blur-sm">
              <div className="relative max-w-md">
                <label htmlFor="plugin-search" className="sr-only">Search plugins</label>
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  id="plugin-search"
                  type="text"
                  placeholder="Search plugins..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full pl-10 pr-4 py-3 bg-white border border-slate-100 rounded-xl focus:outline-none focus:ring-1 focus:ring-primary/20 focus:border-primary/30 transition-all text-sm placeholder:text-slate-400"
                />
              </div>
            </div>
            <div className="flex-1 overflow-y-auto pr-2">
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {filteredPlugins.map(plugin => (
                  <div
                    key={plugin.id}
                    onClick={() => setSelectedPlugin(plugin)}
                    className={`group glass-card p-6 hover:border-primary/20 hover:bg-slate-50/50 transition-all cursor-pointer relative overflow-hidden ${
                      !isPluginActive(plugin.id) ? 'bg-slate-50/60 border-slate-200' : ''
                    }`}
                  >
                    <div className="flex justify-between items-start mb-4">
                      <div className={`p-2 rounded-lg ${isPluginActive(plugin.id) ? 'bg-primary/10 text-primary' : 'bg-slate-100 text-slate-400'}`}>
                        <Zap className="w-5 h-5" />
                      </div>

                      <Toggle
                        checked={isPluginActive(plugin.id)}
                        onChange={(e) => toggleResource('plugins', plugin.id, e)}
                        aria-label={`Toggle ${plugin.name} active status`}
                      />
                    </div>

                    <h2 className="break-words text-lg font-semibold tracking-tight group-hover:text-primary transition-colors mb-2">
                      {plugin.name}
                    </h2>
                    <p className="text-sm text-slate-500 line-clamp-3 font-medium leading-relaxed">
                      {plugin.description}
                    </p>
                    <div className="mt-6 flex items-center text-[11px] font-semibold uppercase tracking-wider text-primary/60 group-hover:text-primary transition-all group-hover:translate-x-1">
                      View details <ChevronRight className="w-3 h-3 ml-1" />
                    </div>

                    <div className={`absolute top-0 right-0 w-1 h-full transition-all ${
                      isPluginActive(plugin.id) ? 'bg-primary' : 'bg-slate-200'
                    }`} />
                  </div>
                ))}
              </div>
              {filteredPlugins.length === 0 && (
                <div className="text-center py-20 text-slate-400 glass-card">
                  No plugins found in this category.
                </div>
              )}
            </div>
          </div>
        )}
      </div>
      {toggleError && (
        <div className="fixed bottom-4 right-4 p-4 bg-red-50 border border-red-200 text-red-600 rounded-xl text-sm font-medium shadow-lg">
          {toggleError}
        </div>
      )}
    </div>
  );
};

export default PluginGallery;
