import { useProject } from '../context/ProjectContext';
import { Globe, ChevronDown } from 'lucide-react';

export default function ProjectSwitcher() {
  const { currentGroup, setCurrentGroup, availableGroups } = useProject();
  return (
    <div className="relative group">
      <button className="flex items-center gap-2 px-4 py-2 bg-white/50 backdrop-blur-md border border-slate-100 rounded-xl hover:bg-white transition-all shadow-sm">
        <Globe size={16} className="text-primary" />
        <span className="text-sm font-semibold capitalize">{currentGroup}</span>
        <ChevronDown size={14} className="text-slate-400 group-hover:rotate-180 transition-transform" />
      </button>
      <div className="absolute right-0 mt-2 w-48 bg-white border border-slate-100 rounded-xl shadow-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50 p-2">
        {availableGroups.map(group => (
          <button
            key={group}
            onClick={() => setCurrentGroup(group)}
            className={`w-full text-left px-4 py-2 rounded-lg text-sm capitalize transition-colors ${
              currentGroup === group ? 'bg-primary/10 text-primary font-bold' : 'hover:bg-slate-50 text-slate-600'
            }`}
          >
            {group}
          </button>
        ))}
      </div>
    </div>
  );
}
