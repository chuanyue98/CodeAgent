import { useState, useMemo, useEffect } from 'react';
import { Search, Filter, ChevronDown, ChevronUp, Clock, DollarSign, FileText, Cpu } from 'lucide-react';
import { fetchSessions, type SessionUsage, fmtCost, fmtTokens } from '../api/analytics';

type SortKey = 'lastActivity' | 'cost' | 'tokens';
type SortDir = 'asc' | 'desc';

export default function SessionsPage() {
  const [sessions, setSessions] = useState<SessionUsage[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [selectedEngines, setSelectedEngines] = useState<string[]>([]);
  const [sortKey, setSortKey] = useState<SortKey>('lastActivity');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    fetchSessions(500).then(data => {
      setSessions(data);
      setLoading(false);
    });
  }, []);

  const engines = useMemo(() => {
    const set = new Set(sessions.map(s => s.target));
    return Array.from(set).sort();
  }, [sessions]);

  const filtered = useMemo(() => {
    let result = sessions;
    if (search) {
      const q = search.toLowerCase();
      result = result.filter(s =>
        s.projectPath.toLowerCase().includes(q) ||
        s.sessionId.toLowerCase().includes(q)
      );
    }
    if (selectedEngines.length > 0) {
      result = result.filter(s => selectedEngines.includes(s.target));
    }
    result = [...result].sort((a, b) => {
      let cmp = 0;
      if (sortKey === 'lastActivity') cmp = a.lastActivity.localeCompare(b.lastActivity);
      else if (sortKey === 'cost') cmp = a.cost - b.cost;
      else if (sortKey === 'tokens') cmp = (a.inputTokens + a.outputTokens) - (b.inputTokens + b.outputTokens);
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return result;
  }, [sessions, search, selectedEngines, sortKey, sortDir]);

  const toggleEngine = (engine: string) => {
    setSelectedEngines(prev =>
      prev.includes(engine) ? prev.filter(e => e !== engine) : [...prev, engine]
    );
  };

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortKey(key); setSortDir('desc'); }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <span className="text-sm text-slate-400">Loading sessions...</span>
      </div>
    );
  }

  return (
    <div className="flex gap-4 h-full">
      <div className="w-56 shrink-0 glass-card p-4 space-y-4">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">
          <Filter className="w-4 h-4" /> Filters
        </div>

        <div>
          <label className="text-xs text-slate-400 font-medium block mb-1">Search</label>
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Project or session..."
              className="w-full pl-7 pr-2 py-1.5 text-xs border border-slate-200 rounded-lg bg-white focus:outline-none focus:border-primary"
            />
          </div>
        </div>

        <div>
          <label className="text-xs text-slate-400 font-medium block mb-1">Engine</label>
          <div className="space-y-1">
            {engines.map(eng => (
              <button
                key={eng}
                onClick={() => toggleEngine(eng)}
                className={`w-full text-left px-2 py-1 rounded-md text-xs transition-colors ${
                  selectedEngines.includes(eng)
                    ? 'bg-slate-100 text-slate-800 font-medium'
                    : 'text-slate-500 hover:bg-slate-50'
                }`}
              >
                {eng}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="flex-1 min-w-0 glass-card p-5">
        <div className="flex items-center justify-between mb-4">
          <p className="text-xs text-slate-400 font-medium">
            {filtered.length} session{filtered.length !== 1 ? 's' : ''}
          </p>
          <div className="flex gap-2">
            {(['lastActivity', 'cost', 'tokens'] as SortKey[]).map(key => (
              <button
                key={key}
                onClick={() => toggleSort(key)}
                className={`px-2 py-1 text-xs rounded-md border transition-colors ${
                  sortKey === key
                    ? 'bg-slate-100 border-slate-300 text-slate-800'
                    : 'border-slate-200 text-slate-500 hover:bg-slate-50'
                }`}
              >
                {key === 'lastActivity' ? 'Date' : key === 'cost' ? 'Cost' : 'Tokens'}
                {sortKey === key && (sortDir === 'asc' ? ' ↑' : ' ↓')}
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-2">
          {filtered.map(session => {
            const isExpanded = expandedId === session.sessionId;
            const totalTokens = session.inputTokens + session.outputTokens;
            return (
              <div
                key={session.sessionId}
                className="border border-slate-100 rounded-xl p-4 hover:bg-slate-50/60 transition-colors"
              >
                <div
                  className="flex items-center justify-between cursor-pointer"
                  onClick={() => setExpandedId(isExpanded ? null : session.sessionId)}
                >
                  <div className="flex items-center gap-3 min-w-0 flex-1">
                    <div className="flex flex-col min-w-0">
                      <span className="text-sm font-medium text-slate-700 truncate">
                        {session.projectPath.split(/[\\/]/).pop() || session.projectPath || '—'}
                      </span>
                      <span className="text-xs text-slate-400">
                        {session.projectPath}
                      </span>
                    </div>
                    <span className="shrink-0 px-2 py-0.5 text-[10px] font-bold rounded-full uppercase bg-slate-100 text-slate-600">
                      {session.target}
                    </span>
                  </div>
                  <div className="flex items-center gap-4 shrink-0">
                    <span className="text-xs text-slate-500 flex items-center gap-1">
                      <FileText className="w-3 h-3" />{fmtTokens(totalTokens)}
                    </span>
                    <span className="text-xs text-slate-500 flex items-center gap-1">
                      <DollarSign className="w-3 h-3" />{fmtCost(session.cost)}
                    </span>
                    <span className="text-xs text-slate-400 flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      {new Date(session.lastActivity).toLocaleDateString()}
                    </span>
                    {isExpanded ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
                  </div>
                </div>

                {isExpanded && (
                  <div className="mt-3 pt-3 border-t border-slate-100">
                    <p className="text-xs text-slate-400 font-medium mb-2">Model Breakdown</p>
                    {session.modelBreakdowns?.length > 0 ? (
                      <div className="space-y-1.5">
                        {session.modelBreakdowns.map((mb, i) => (
                          <div key={i} className="flex items-center justify-between text-xs">
                            <span className="text-slate-600 font-mono">{mb.modelName}</span>
                            <div className="flex gap-3 text-slate-500">
                              <span>in: {fmtTokens(mb.inputTokens)}</span>
                              <span>out: {fmtTokens(mb.outputTokens)}</span>
                              <span className="font-semibold text-slate-700">{fmtCost(mb.cost)}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-slate-400">No model breakdown available</p>
                    )}
                    <div className="mt-2 pt-2 border-t border-slate-50 flex gap-4 text-xs text-slate-500">
                      <span>Cache write: {fmtTokens(session.cacheCreationTokens)}</span>
                      <span>Cache read: {fmtTokens(session.cacheReadTokens)}</span>
                      <span className="font-mono text-slate-400 truncate">{session.sessionId}</span>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
          {filtered.length === 0 && (
            <p className="text-sm text-slate-400 text-center py-8">No sessions match your filters</p>
          )}
        </div>
      </div>
    </div>
  );
}
