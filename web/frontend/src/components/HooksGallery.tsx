import React, { useState, useEffect } from 'react';
import { Search, Anchor, Terminal, Info, ExternalLink } from 'lucide-react';
import { useProject } from '../context/ProjectContext';

interface Hook {
  id: string;
  name: string;
  event: string;
  description: string;
  path: string;
}

const HooksGallery: React.FC = () => {
  const { currentGroup, groups, refreshConfig } = useProject();
  const [hooks, setHooks] = useState<Hook[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');

  useEffect(() => {
    const fetchHooks = async () => {
      try {
        const response = await fetch('/api/hooks');
        if (!response.ok) {
          throw new Error('Failed to fetch hooks');
        }
        const data = await response.json();
        const hooksArray = Array.isArray(data) ? data : (data.hooks || []);
        setHooks(hooksArray);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'An unknown error occurred');
      } finally {
        setLoading(false);
      }
    };

    fetchHooks();
  }, []);

  const isHookActive = (hookId: string) => {
    return groups[currentGroup]?.hooks?.includes(hookId) || false;
  };

  const toggleHookStatus = async (hookId: string) => {
    if (!currentGroup) return;

    try {
      const currentGroupDef = groups[currentGroup] || { skills: [], prompts: [], hooks: [] };
      const newHooks = [...currentGroupDef.hooks];
      const index = newHooks.indexOf(hookId);

      if (index > -1) {
        newHooks.splice(index, 1);
      } else {
        newHooks.push(hookId);
      }

      await fetch(`/api/groups/${currentGroup}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...currentGroupDef, hooks: newHooks }),
      });

      await refreshConfig();
    } catch (err) {
      console.error('Failed to toggle hook:', err);
      setError(err instanceof Error ? err.message : 'Failed to toggle hook');
    }
  };

  const filteredHooks = hooks.filter(hook =>
    hook.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    hook.description.toLowerCase().includes(searchTerm.toLowerCase()) ||
    hook.event.toLowerCase().includes(searchTerm.toLowerCase())
  );

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
    <div className="flex flex-col h-full overflow-hidden p-6 gap-6">
      <div className="flex items-center justify-between glass-card p-6 bg-slate-50/30 backdrop-blur-sm">
        <div className="relative max-w-md w-full">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            placeholder="Search hooks..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-10 pr-4 py-3 bg-white border border-slate-100 rounded-xl focus:outline-none focus:ring-1 focus:ring-primary/20 focus:border-primary/30 transition-all text-sm placeholder:text-slate-400"
          />
        </div>
        <div className="flex items-center gap-2 px-4 py-2 bg-primary/15 text-cyan-800 rounded-xl text-sm font-semibold">
          <Anchor className="w-4 h-4" />
          <span>{hooks.length} Total Hooks</span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto pr-2">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredHooks.map(hook => {
            const active = isHookActive(hook.id);
            return (
              <div
                key={hook.id}
                className={`group glass-card p-6 transition-all relative overflow-hidden flex flex-col ${
                  !active ? 'opacity-70 grayscale-[0.5]' : ''
                }`}
              >
                <div className="flex justify-between items-start mb-4">
                  <div className="flex items-center gap-2">
                    <div className={`p-2 rounded-lg ${active ? 'bg-primary/10 text-primary' : 'bg-slate-100 text-slate-400'}`}>
                      <Anchor className="w-5 h-5" />
                    </div>
                    <span className={`text-[10px] px-2 py-0.5 rounded-full border font-bold uppercase tracking-wider ${
                      active
                        ? 'border-emerald-100 bg-emerald-50 text-emerald-600'
                        : 'border-slate-100 bg-slate-50 text-slate-400'
                    }`}>
                      {hook.event}
                    </span>
                  </div>

                  {/* Toggle Switch */}
                  <button
                    onClick={() => toggleHookStatus(hook.id)}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none ${
                      active ? 'bg-primary' : 'bg-slate-200'
                    }`}
                  >
                    <span
                      className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                        active ? 'translate-x-6' : 'translate-x-1'
                      }`}
                    />
                  </button>
                </div>

                <h3 className="text-lg font-semibold tracking-tight mb-2 group-hover:text-primary transition-colors">
                  {hook.name}
                </h3>

                <p className="text-sm text-slate-500 line-clamp-2 font-medium leading-relaxed mb-4 flex-1">
                  {hook.description}
                </p>

                <div className="mt-auto pt-4 border-t border-slate-50 space-y-3">
                  <div className="flex items-center gap-2 text-[11px] text-slate-400 font-mono bg-slate-50/50 p-2 rounded-lg overflow-hidden whitespace-nowrap text-ellipsis">
                    <Terminal className="w-3 h-3 flex-shrink-0" />
                    <span className="truncate">{hook.path}</span>
                  </div>

                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5 text-[11px] font-bold text-slate-400 uppercase tracking-widest">
                      <Info className="w-3 h-3" />
                      <span>Status: {active ? 'Active' : 'Inactive'}</span>
                    </div>
                    <button className="p-1.5 hover:bg-slate-100 rounded-lg transition-colors text-slate-400 hover:text-primary">
                      <ExternalLink className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                <div className={`absolute top-0 right-0 w-1 h-full transition-all ${
                  active ? 'bg-primary' : 'bg-slate-200'
                }`} />
              </div>
            );
          })}
        </div>

        {filteredHooks.length === 0 && (
          <div className="text-center py-20 text-slate-400 glass-card">
            No hooks found matching your search.
          </div>
        )}
      </div>
    </div>
  );
};

export default HooksGallery;
