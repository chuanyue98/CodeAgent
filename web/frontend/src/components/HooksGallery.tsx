import React, { useState, useMemo } from 'react';
import { Search, Anchor, Terminal, Info } from 'lucide-react';
import { useProject } from '../context/ProjectContext';
import Toggle from './shared/Toggle';
import ErrorState from './shared/ErrorState';
import LoadingState from './shared/LoadingState';
import useResourceData from '../hooks/useResourceData';
import useResourceToggle from '../hooks/useResourceToggle';
import Toast from './shared/Toast';

interface Hook {
  id: string;
  name: string;
  event: string;
  description: string;
  path: string;
}

const HooksGallery: React.FC = () => {
  const { currentGroup, groups } = useProject();
  const { data: rawData, loading, error, refetch } = useResourceData<Hook[] | { hooks: Hook[] }>('/api/hooks');
  const { toggleResource, toggleError, dismissToggleError } = useResourceToggle();
  const [searchTerm, setSearchTerm] = useState('');

  const hooks = useMemo(() => {
    if (!rawData) return [];
    return Array.isArray(rawData) ? rawData : (rawData.hooks || []);
  }, [rawData]);

  const isHookActive = (hookId: string) => {
    return groups[currentGroup]?.hooks?.includes(hookId) || false;
  };

  const filteredHooks = hooks.filter(hook =>
    hook.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    hook.description.toLowerCase().includes(searchTerm.toLowerCase()) ||
    hook.event.toLowerCase().includes(searchTerm.toLowerCase())
  );

  if (loading) {
    return <LoadingState />;
  }

  if (error) {
    return <ErrorState message={error} onRetry={refetch} />;
  }

  return (
    <div className="flex flex-col h-full overflow-hidden p-6 gap-6">
      <div className="flex items-center justify-between glass-card p-6 bg-slate-50/30 backdrop-blur-sm">
        <div className="relative max-w-md w-full">
          <label htmlFor="hook-search" className="sr-only">Search hooks</label>
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            id="hook-search"
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
                  !active ? 'bg-slate-50/60 border-slate-200' : ''
                }`}
              >
                <div className="flex justify-between items-start mb-4">
                  <div className="flex items-center gap-2">
                    <div className={`p-2 rounded-lg ${active ? 'bg-primary/10 text-primary' : 'bg-slate-100 text-slate-400'}`}>
                      <Anchor className="w-5 h-5" />
                    </div>
                    <span className={`text-[10px] px-2 py-0.5 rounded-full border font-bold uppercase tracking-wider ${
                      active
                        ? 'border-emerald-100 bg-emerald-50 text-emerald-700'
                        : 'border-slate-100 bg-slate-50 text-slate-600'
                    }`}>
                      {hook.event}
                    </span>
                  </div>

                  <Toggle
                    checked={active}
                    onChange={() => toggleResource('hooks', hook.id)}
                    aria-label={`Toggle ${hook.name} active status`}
                    size="md"
                  />
                </div>

                <h2 className="text-lg font-semibold tracking-tight mb-2 group-hover:text-primary transition-colors">
                  {hook.name}
                </h2>

                <p className="text-sm text-slate-500 line-clamp-2 font-medium leading-relaxed mb-4 flex-1">
                  {hook.description}
                </p>

                <div className="mt-auto pt-4 border-t border-slate-50 space-y-3">
                  <div className="flex items-center gap-2 text-[11px] text-slate-400 font-mono bg-slate-50/50 p-2 rounded-lg overflow-hidden whitespace-nowrap text-ellipsis">
                    <Terminal className="w-3 h-3 flex-shrink-0" />
                    <span className="truncate">{hook.path}</span>
                  </div>

                  <div className="flex items-center gap-1.5 text-[11px] font-bold text-slate-500 uppercase tracking-widest">
                    <Info className="w-3 h-3" />
                    <span>Status: {active ? 'Active' : 'Inactive'}</span>
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
          <div className="text-center py-20 text-slate-500 glass-card">
            No hooks found matching your search.
          </div>
        )}
      </div>
      {toggleError && <Toast message={toggleError} onDismiss={dismissToggleError} />}
    </div>
  );
};

export default HooksGallery;
