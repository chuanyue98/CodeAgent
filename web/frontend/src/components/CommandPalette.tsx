import { useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';
import { useNavigate } from 'react-router';
import { Search, SquareStack, MessageSquare, ListChecks, FolderGit2 } from 'lucide-react';
import { useProject } from '../context/ProjectContext';
import { PAGE_LABELS } from '../navigation';
import { fetchSessions, type SessionUsage } from '../api/analytics';
import request from '../utils/request';

interface TaskSummary {
  name: string;
  title: string;
  description: string;
}

interface PaletteItem {
  id: string;
  label: string;
  hint: string;
  section: 'Navigate' | 'Project' | 'Session' | 'Task' | 'Workspace';
  icon: typeof SquareStack;
  run: () => void;
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable;
}

export default function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const [sessions, setSessions] = useState<SessionUsage[]>([]);
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [dataLoaded, setDataLoaded] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const { availableGroups, currentGroup, setCurrentGroup, projects, setSelectedWorkspace } = useProject();

  // Sessions/tasks are only fetched once the palette is actually opened, and
  // only the first time -- there's no reason to hit these endpoints on every
  // page load just so ⌘K happens to be fast the first time it's used.
  useEffect(() => {
    if (!open || dataLoaded) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDataLoaded(true);
    fetchSessions(200)
      .then(setSessions)
      .catch(() => setSessions([]));
    request<TaskSummary[]>('/api/tasks')
      .then(setTasks)
      .catch(() => setTasks([]));
  }, [open, dataLoaded]);

  const items = useMemo<PaletteItem[]>(() => {
    const navItems: PaletteItem[] = Object.entries(PAGE_LABELS).map(([path, label]) => ({
      id: `nav:${path}`,
      label,
      hint: path,
      section: 'Navigate',
      icon: SquareStack,
      run: () => navigate(path),
    }));
    const groupItems: PaletteItem[] = availableGroups.map(group => ({
      id: `group:${group}`,
      label: `Switch to ${group}`,
      hint: group === currentGroup ? 'current resource group' : 'resource group',
      section: 'Project',
      icon: SquareStack,
      run: () => setCurrentGroup(group),
    }));
    const workspaceItems: PaletteItem[] = projects
      .filter(project => project.path.trim())
      .map(project => ({
        id: `workspace:${project.path}`,
        label: project.path.split(/[\\/]/).filter(Boolean).pop() || project.path,
        hint: project.path,
        section: 'Workspace',
        icon: FolderGit2,
        run: () => {
          setSelectedWorkspace(project.path);
          navigate('/agent/web');
        },
      }));
    const sessionItems: PaletteItem[] = sessions.map(session => ({
      id: `session:${session.target}:${session.sessionId}`,
      label: session.projectPath.split(/[\\/]/).filter(Boolean).pop() || session.sessionId,
      hint: `${session.target} session · ${session.projectPath}`,
      section: 'Session',
      icon: MessageSquare,
      run: () => navigate(`/activity/history?session=${encodeURIComponent(session.sessionId)}`),
    }));
    const taskItems: PaletteItem[] = tasks.map(task => ({
      id: `task:${task.name}`,
      label: task.title || task.name,
      hint: task.description || `task · ${task.name}`,
      section: 'Task',
      icon: ListChecks,
      run: () => navigate(`/automations/tasks?task=${encodeURIComponent(task.name)}`),
    }));
    return [...navItems, ...workspaceItems, ...sessionItems, ...taskItems, ...groupItems];
  }, [navigate, availableGroups, currentGroup, setCurrentGroup, projects, setSelectedWorkspace, sessions, tasks]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter(
      item => item.label.toLowerCase().includes(q) || item.hint.toLowerCase().includes(q),
    );
  }, [items, query]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setActiveIndex(0);
  }, [query, open]);

  useEffect(() => {
    function handleGlobalKeyDown(event: KeyboardEvent) {
      const isModK = (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k';
      if (isModK) {
        event.preventDefault();
        setOpen(prev => !prev);
      }
    }
    window.addEventListener('keydown', handleGlobalKeyDown);
    return () => window.removeEventListener('keydown', handleGlobalKeyDown);
  }, []);

  useEffect(() => {
    if (!open) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setQuery('');
    const frame = requestAnimationFrame(() => inputRef.current?.focus());
    return () => cancelAnimationFrame(frame);
  }, [open]);

  const runItem = (item: PaletteItem) => {
    item.run();
    setOpen(false);
  };

  const handleInputKeyDown = (event: ReactKeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActiveIndex(i => Math.min(i + 1, filtered.length - 1));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActiveIndex(i => Math.max(i - 1, 0));
    } else if (event.key === 'Enter') {
      event.preventDefault();
      const item = filtered[activeIndex];
      if (item) runItem(item);
    } else if (event.key === 'Escape') {
      event.preventDefault();
      setOpen(false);
    }
  };

  return (
    <>
      <button
        type="button"
        data-testid="command-palette-trigger"
        onClick={() => setOpen(true)}
        aria-label="Open command palette"
        title="Search (Ctrl/Cmd+K)"
        className="flex items-center gap-1.5 rounded-xl border border-slate-100 bg-white/50 px-3 py-2 text-slate-500 shadow-sm backdrop-blur-md transition-colors hover:bg-white hover:text-slate-800"
      >
        <Search size={16} />
        <kbd className="hidden rounded border border-slate-200 px-1.5 py-0.5 text-[10px] text-slate-400 sm:inline">
          {navigator.platform.toLowerCase().includes('mac') ? '⌘K' : 'Ctrl K'}
        </kbd>
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center bg-slate-900/40 pt-[15vh]"
          role="presentation"
          onClick={() => setOpen(false)}
          onKeyDown={event => {
            if (event.key === 'Escape' && !isEditableTarget(event.target)) setOpen(false);
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Command palette"
            data-testid="command-palette"
            className="glass-card w-full max-w-lg overflow-hidden"
            onClick={event => event.stopPropagation()}
          >
            <div className="flex items-center gap-2 border-b border-slate-100 px-4 py-3">
              <Search size={16} className="shrink-0 text-slate-400" />
              <input
                ref={inputRef}
                value={query}
                onChange={event => setQuery(event.target.value)}
                onKeyDown={handleInputKeyDown}
                placeholder="Go to a page, session, task, workspace…"
                aria-label="Command palette search"
                className="w-full bg-transparent text-sm text-slate-800 outline-none placeholder:text-slate-400"
              />
              <kbd className="hidden shrink-0 rounded border border-slate-200 px-1.5 py-0.5 text-[10px] text-slate-400 sm:inline">
                Esc
              </kbd>
            </div>
            <ul className="max-h-80 overflow-y-auto py-2" role="listbox" aria-label="Command palette results">
              {filtered.length === 0 && (
                <li className="px-4 py-6 text-center text-sm text-slate-400">No matches</li>
              )}
              {filtered.map((item, index) => (
                <li key={item.id} role="option" aria-selected={index === activeIndex}>
                  <button
                    type="button"
                    onMouseEnter={() => setActiveIndex(index)}
                    onClick={() => runItem(item)}
                    className={`flex w-full items-center justify-between gap-3 px-4 py-2 text-left text-sm transition-colors ${
                      index === activeIndex ? 'bg-primary/10 text-primary' : 'text-slate-600 hover:bg-slate-50'
                    }`}
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      <item.icon size={14} className="shrink-0 opacity-60" />
                      <span className="truncate font-medium">{item.label}</span>
                      <span className="shrink-0 text-[10px] uppercase tracking-wide text-slate-400">{item.section}</span>
                    </span>
                    <span className="shrink-0 truncate text-xs text-slate-400 max-w-[45%]">{item.hint}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </>
  );
}
