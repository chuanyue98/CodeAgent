import { useState, useRef, useEffect } from 'react';
import { useProject } from '../context/ProjectContext';
import { Globe, ChevronDown } from 'lucide-react';

export default function ProjectSwitcher() {
  const { currentGroup, setCurrentGroup, availableGroups } = useProject();
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

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`Project group: ${currentGroup}`}
        className="flex max-w-44 items-center gap-2 px-3 md:px-4 py-2 bg-white/50 backdrop-blur-md border border-slate-100 rounded-xl hover:bg-white transition-colors shadow-sm"
      >
        <Globe size={16} className="text-primary" />
        <span className="truncate text-sm font-semibold capitalize">{currentGroup}</span>
        <ChevronDown size={14} className={`text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div role="listbox" className="absolute right-0 mt-2 w-48 max-w-[calc(100vw-1rem)] bg-white border border-slate-100 rounded-xl shadow-xl z-50 p-2">
          {availableGroups.map(group => (
            <button
              key={group}
              role="option"
              aria-selected={currentGroup === group}
              onClick={() => { setCurrentGroup(group); setOpen(false); }}
              className={`w-full text-left px-4 py-2 rounded-lg text-sm capitalize transition-colors ${
                currentGroup === group ? 'bg-primary/10 text-primary font-bold' : 'hover:bg-slate-50 text-slate-600'
              }`}
            >
              {group}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
