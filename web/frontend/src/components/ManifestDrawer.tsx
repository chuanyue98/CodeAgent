import { Package, Anchor, GitBranch, Zap } from 'lucide-react';
import { useProject } from '../context/ProjectContext';

export default function ManifestDrawer() {
  const { currentGroup, groups } = useProject();
  const def = groups[currentGroup] || { skills: [], prompts: [], hooks: [], plugins: [] };

  const stats = [
    { icon: Package, label: 'Skills',  count: def.skills?.length ?? 0,  color: 'text-primary bg-primary/8' },
    { icon: Anchor,  label: 'Hooks',   count: def.hooks?.length ?? 0,   color: 'text-orange-500 bg-orange-50' },
    { icon: GitBranch, label: 'Prompts', count: def.prompts?.length ?? 0, color: 'text-emerald-500 bg-emerald-50' },
    { icon: Zap, label: 'Plugins', count: def.plugins?.length ?? 0, color: 'text-purple-500 bg-purple-50' },
  ];

  return (
    <div className="w-48 glass-card flex flex-col h-full overflow-hidden">
      <div className="p-5 border-b border-slate-100 bg-slate-50/50">
        <p className="text-xs font-bold uppercase tracking-widest text-slate-500 mb-1">Manifest</p>
        <p className="text-sm font-black text-primary capitalize truncate">{currentGroup}</p>
      </div>
      <div className="flex-1 p-4 space-y-3">
        {stats.map(({ icon: Icon, label, count, color }) => (
          <div key={label} className="flex items-center justify-between px-3 py-2.5 rounded-xl bg-slate-50/50 border border-slate-100">
            <div className="flex items-center gap-2">
              <div className={`p-1.5 rounded-lg ${color}`}>
                <Icon size={13} />
              </div>
              <span className="text-xs font-medium text-slate-500">{label}</span>
            </div>
            <span className="text-sm font-bold text-slate-700">{count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
