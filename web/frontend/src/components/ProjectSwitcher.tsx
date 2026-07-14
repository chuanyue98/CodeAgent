import { useState, useRef, useEffect } from 'react';
import { useProject } from '../context/ProjectContext';
import { Layers, ChevronDown } from 'lucide-react';

export default function ProjectSwitcher() {
  const { currentGroup, setCurrentGroup, availableGroups, groups } = useProject();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const current = groups[currentGroup];
  const resourceCount = (current?.skills?.length ?? 0)
    + (current?.prompts?.length ?? 0)
    + (current?.hooks?.length ?? 0)
    + (current?.plugins?.length ?? 0);

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`Resource group: ${currentGroup}`}
        className="flex max-w-52 items-center gap-2 px-3 md:px-4 py-2 bg-white/50 backdrop-blur-md border border-slate-100 rounded-xl hover:bg-white transition-colors shadow-sm"
      >
        <Layers size={16} className="text-primary" />
        <span className="truncate text-sm font-semibold"><span className="text-slate-400">Group · </span>{currentGroup}</span>
        <ChevronDown size={14} className={`text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="absolute right-0 z-50 mt-2 w-56 max-w-[calc(100vw-1rem)] overflow-hidden rounded-xl border border-slate-100 bg-white shadow-xl">
          <div className="px-4 pb-1 pt-3 text-[10px] font-semibold uppercase tracking-wider text-slate-400">Resource group</div>
          <div role="listbox" className="p-2 pt-1">
            {availableGroups.map(group => (
              <button
                key={group}
                role="option"
                aria-selected={currentGroup === group}
                onClick={() => { setCurrentGroup(group); setOpen(false); }}
                className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                  currentGroup === group ? 'bg-primary/10 text-primary font-bold' : 'hover:bg-slate-50 text-slate-600'
                }`}
              >
                {group}
              </button>
            ))}
          </div>
          <div className="border-t border-slate-100 bg-slate-50/70 px-4 py-2 text-[11px] text-slate-500">
            {resourceCount} configured resources
          </div>
        </div>
      )}
    </div>
  );
}
