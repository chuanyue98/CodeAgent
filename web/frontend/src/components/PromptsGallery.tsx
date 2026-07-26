import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { BookMarked, ChevronRight, Files, GitBranch, Search } from 'lucide-react';
import { useProject } from '../context/ProjectContext';
import Toggle from './shared/Toggle';
import ErrorState from './shared/ErrorState';
import LoadingState from './shared/LoadingState';
import useResourceData from '../hooks/useResourceData';
import useResourceToggle from '../hooks/useResourceToggle';
import Toast from './shared/Toast';

interface PromptFile {
  name: string;
  path: string;
}

interface PromptGroup {
  id: string;
  name: string;
  description: string;
  readme: string;
  files: PromptFile[];
}

const PromptsGallery: React.FC = () => {
  const { currentGroup, groups } = useProject();
  const { data: rawData, loading, error, refetch } = useResourceData<PromptGroup[] | { prompts: PromptGroup[] }>('/api/prompts');
  const { toggleResource, toggleError, dismissToggleError } = useResourceToggle();
  const [selectedPrompt, setSelectedPrompt] = useState<PromptGroup | null>(null);
  const [searchTerm, setSearchTerm] = useState('');

  const promptGroups = React.useMemo(() => {
    if (!rawData) return [];
    return Array.isArray(rawData) ? rawData : (rawData.prompts || []);
  }, [rawData]);

  const isPromptActive = (promptId: string) => {
    return groups[currentGroup]?.prompts?.includes(promptId) ?? false;
  };

  const filteredPrompts = promptGroups.filter((promptGroup) =>
    promptGroup.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    promptGroup.description.toLowerCase().includes(searchTerm.toLowerCase()) ||
    promptGroup.files.some((file) =>
      file.name.toLowerCase().includes(searchTerm.toLowerCase())
    )
  );

  if (loading) {
    return <LoadingState />;
  }

  if (error) {
    return <ErrorState message={error} onRetry={refetch} />;
  }

  if (selectedPrompt) {
    return (
      <div className="flex h-full overflow-hidden p-6 gap-6">
        {/* key on id so the entrance replays each time a different prompt is opened. */}
        <div key={selectedPrompt.id} className="animate-fade-rise stagger-2 flex-1 glass-card flex flex-col overflow-hidden">
          <div className="p-6 border-b border-slate-200 flex items-center gap-4 bg-white">
            <button
              onClick={() => setSelectedPrompt(null)}
              aria-label="Back to prompt groups"
              className="p-2 hover:bg-slate-100 rounded-xl transition-all border border-slate-200"
            >
              <ChevronRight className="w-5 h-5 rotate-180" />
            </button>
            <div className="flex-1">
              <span className="text-[10px] uppercase tracking-widest text-primary font-bold">Prompt Group</span>
              <h1 className="text-2xl font-semibold tracking-tight capitalize text-slate-900">{selectedPrompt.name}</h1>
            </div>
            <div className="flex items-center gap-3 px-4 py-2 bg-slate-50 rounded-xl border border-slate-200">
              <span className="text-xs font-semibold text-slate-600">Active in {currentGroup}</span>
              <Toggle
                checked={isPromptActive(selectedPrompt.id)}
                onChange={(e) => toggleResource('prompts', selectedPrompt.id, e)}
                aria-label={isPromptActive(selectedPrompt.id) ? 'Deactivate prompt group' : 'Activate prompt group'}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] flex-1 min-h-0">
            <div className="border-r border-slate-200 bg-slate-50 p-6 overflow-y-auto">
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-slate-500 mb-4">
                <Files className="w-4 h-4 text-primary" />
                Files in Group
              </div>
              <div className="space-y-2">
                {selectedPrompt.files.map((file) => (
                  <div
                    key={file.path}
                    className="rounded-xl border border-slate-200 bg-white px-4 py-3"
                  >
                    <div className="text-sm font-semibold text-slate-800">{file.name}</div>
                    <div className="mt-1 text-[11px] font-mono text-slate-500 break-all">
                      {file.path}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="overflow-y-auto p-8 bg-white prose prose-slate max-w-none prose-headings:text-slate-900 prose-p:text-slate-700 prose-li:text-slate-700 prose-strong:text-slate-900">
              <ReactMarkdown
                components={{
                  code({ className, children, ...props }) {
                    const isCodeBlock = className && className.startsWith('language-');
                    return isCodeBlock ? (
                      <code className={`${className} font-mono`} {...props}>
                        {children}
                      </code>
                    ) : (
                      <code
                        className="font-mono bg-slate-100 border border-slate-200 px-1.5 py-0.5 rounded text-cyan-700 text-[0.875em]"
                        {...props}
                      >
                        {children}
                      </code>
                    );
                  },
                  pre({ children, ...props }) {
                    return (
                      <pre
                        className="!bg-slate-900 !text-slate-100 p-5 rounded-xl shadow-inner border border-slate-700 overflow-x-auto"
                        {...props}
                      >
                        {children}
                      </pre>
                    );
                  },
                }}
              >
                {selectedPrompt.readme}
              </ReactMarkdown>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden p-6 gap-6">
      <div className="animate-fade-rise stagger-1 flex items-center justify-between glass-card p-6 bg-slate-50/30 backdrop-blur-sm">
        <div className="relative max-w-md w-full">
          <label htmlFor="prompt-search" className="sr-only">Search prompt groups</label>
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            id="prompt-search"
            type="text"
            placeholder="Search prompt groups..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-10 pr-4 py-3 bg-white border border-slate-100 rounded-xl focus:outline-none focus:ring-1 focus:ring-primary/20 focus:border-primary/30 transition-all text-sm placeholder:text-slate-400"
          />
        </div>
        <div className="flex items-center gap-2 px-4 py-2 bg-emerald-50 text-emerald-700 rounded-xl text-sm font-semibold">
          <GitBranch className="w-4 h-4" />
          <span>{promptGroups.length} Prompt Groups</span>
        </div>
      </div>

      <div className="custom-scrollbar flex-1 overflow-y-auto pr-2">
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          {filteredPrompts.map((promptGroup, i) => {
            const active = isPromptActive(promptGroup.id);
            // Cap stagger at 6 — long galleries shouldn't cascade forever.
            const stagger = `stagger-${Math.min(i + 2, 7)}`;
            return (
              <div
                key={promptGroup.id}
                onClick={() => setSelectedPrompt(promptGroup)}
                className={`animate-fade-rise ${stagger} group glass-card p-6 hover:border-primary/20 hover:bg-slate-50/50 transition-all cursor-pointer relative overflow-hidden ${
                  !active ? 'bg-slate-50/60 border-slate-200' : ''
                }`}
              >
                <div className="flex justify-between items-start mb-4">
                  <div className={`p-2 rounded-lg ${active ? 'bg-emerald-50 text-emerald-600' : 'bg-slate-100 text-slate-400'}`}>
                    <BookMarked className="w-5 h-5" />
                  </div>

                  <Toggle
                    checked={active}
                    onChange={(e) => toggleResource('prompts', promptGroup.id, e)}
                    aria-label={`Toggle ${promptGroup.name} active status`}
                  />
                </div>

                <h2 className="break-words text-lg font-semibold tracking-tight group-hover:text-primary transition-colors mb-2 capitalize">
                  {promptGroup.name}
                </h2>
                <p className="text-sm text-slate-500 line-clamp-3 font-medium leading-relaxed">
                  {promptGroup.description}
                </p>

                <div className="mt-4 flex flex-wrap gap-2">
                  {promptGroup.files.slice(0, 4).map((file) => (
                    <span
                      key={file.path}
                      className="text-[10px] px-2 py-1 rounded-full border border-slate-100 bg-slate-50 text-slate-600 font-semibold"
                    >
                      {file.name}
                    </span>
                  ))}
                  {promptGroup.files.length > 4 && (
                    <span className="text-[10px] px-2 py-1 rounded-full border border-slate-100 bg-slate-50 text-slate-600 font-semibold">
                      +{promptGroup.files.length - 4}
                    </span>
                  )}
                </div>

                <div className="mt-6 flex items-center justify-between text-[11px] font-bold uppercase tracking-widest">
                  <span className="text-slate-500">{promptGroup.files.length} files</span>
                  <span className="text-primary/70 group-hover:text-primary transition-all group-hover:translate-x-1 flex items-center">
                    View group <ChevronRight className="w-3 h-3 ml-1" />
                  </span>
                </div>

                <div className={`absolute top-0 right-0 w-1 h-full transition-all ${
                  active ? 'bg-primary' : 'bg-slate-200'
                }`} />
              </div>
            );
          })}
        </div>

        {filteredPrompts.length === 0 && (
          <div className="text-center py-20 text-slate-500 glass-card">
            No prompt groups found matching your search.
          </div>
        )}
      </div>
      {toggleError && <Toast message={toggleError} onDismiss={dismissToggleError} />}
    </div>
  );
};

export default PromptsGallery;
