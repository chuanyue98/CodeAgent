import React, { useState, useEffect } from 'react';
import { Search, BookOpen, Layers, Terminal, Globe, Cpu, ChevronRight, Zap } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { useProject } from '../context/ProjectContext';

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
  const { currentGroup, groups, refreshConfig } = useProject();
  const [pluginsData, setPluginsData] = useState<PluginsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [selectedPlugin, setSelectedPlugin] = useState<Plugin | null>(null);
  const [searchTerm, setSearchTerm] = useState('');

  useEffect(() => {
    const fetchPlugins = async () => {
      try {
        const response = await fetch('/api/plugins');
        if (!response.ok) {
          throw new Error('Failed to fetch plugins');
        }
        const data: PluginsData = await response.json();
        setPluginsData(data);
        const categories = Object.keys(data);
        if (categories.length > 0) {
          setSelectedCategory(categories[0]);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'An unknown error occurred');
      } finally {
        setLoading(false);
      }
    };

    fetchPlugins();
  }, []);

  const togglePluginStatus = async (pluginId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!currentGroup) return;

    try {
      const currentGroupDef = groups[currentGroup] || { skills: [], prompts: [], hooks: [], plugins: [] };
      const newPlugins = [...(currentGroupDef.plugins || [])];
      const index = newPlugins.indexOf(pluginId);

      if (index > -1) {
        newPlugins.splice(index, 1);
      } else {
        newPlugins.push(pluginId);
      }

      await fetch(`/api/groups/${currentGroup}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...currentGroupDef, plugins: newPlugins }),
      });

      await refreshConfig();
    } catch (err) {
      console.error('Failed to toggle plugin:', err);
    }
  };

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
    return (
      <div className="flex items-center justify-center h-96">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8 text-center text-red-500">
        <p>Error: {error}</p>
        <button
          onClick={() => window.location.reload()}
          className="mt-4 px-4 py-2 bg-primary text-white rounded-md hover:bg-primary/90 transition-colors"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="flex h-full overflow-hidden p-6 gap-6">
      {/* Sidebar Categories */}
      <div className="w-64 glass-card flex flex-col overflow-hidden">
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
                <button
                  onClick={(e) => togglePluginStatus(selectedPlugin.id, e)}
                  className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none ${
                    isPluginActive(selectedPlugin.id) ? 'bg-primary' : 'bg-slate-200'
                  }`}
                >
                  <span
                    className={`inline-block h-3 w-3 transform rounded-full bg-white transition-transform ${
                      isPluginActive(selectedPlugin.id) ? 'translate-x-5' : 'translate-x-1'
                    }`}
                  />
                </button>
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
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
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
                      !isPluginActive(plugin.id) ? 'opacity-70' : ''
                    }`}
                  >
                    <div className="flex justify-between items-start mb-4">
                      <div className={`p-2 rounded-lg ${isPluginActive(plugin.id) ? 'bg-primary/10 text-primary' : 'bg-slate-100 text-slate-400'}`}>
                        <Zap className="w-5 h-5" />
                      </div>

                      {/* Toggle Switch */}
                      <button
                        onClick={(e) => togglePluginStatus(plugin.id, e)}
                        className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none ${
                          isPluginActive(plugin.id) ? 'bg-primary' : 'bg-slate-200'
                        }`}
                      >
                        <span
                          className={`inline-block h-3 w-3 transform rounded-full bg-white transition-transform ${
                            isPluginActive(plugin.id) ? 'translate-x-5' : 'translate-x-1'
                          }`}
                        />
                      </button>
                    </div>

                    <h3 className="text-lg font-semibold tracking-tight group-hover:text-primary transition-colors mb-2">
                      {plugin.name}
                    </h3>
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
    </div>
  );
};

export default PluginGallery;
