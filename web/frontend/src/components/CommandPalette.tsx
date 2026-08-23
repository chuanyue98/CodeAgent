import { useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent, MouseEvent as ReactMouseEvent } from 'react';
import { useNavigate } from 'react-router';
import { Search, SquareStack, MessageSquare, ListChecks, FolderGit2, Pin, PinOff } from 'lucide-react';
import { useProject } from '../context/ProjectContext';
import { PAGE_LABELS } from '../navigation';
import { fetchSessions, type SessionUsage } from '../api/analytics';
import { buildSessionLink } from '../utils/sessionLink';
import request from '../utils/request';
import Modal from './shared/Modal';

interface TaskSummary {
  name: string;
  title: string;
  description: string;
}

interface PaletteItem {
  id: string;
  label: string;
  hint: string;
  section: '已固定' | '跳转' | '资源组' | '会话' | '任务' | '工作区';
  icon: typeof SquareStack;
  run: () => void;
  /**
   * Stable key used for the pinned-ids set. Present only on pinnable items
   * (Workspace/Task and their "Pinned" section clone) -- the clone gets its
   * own `id` (for React's list key) but keeps the *same* pinKey so toggling
   * pin state from either copy stays in sync.
   */
  pinKey?: string;
}

const PINNED_STORAGE_KEY = 'codeagent.pinnedPaletteItems';

function loadPinnedIds(): Set<string> {
  try {
    const raw = localStorage.getItem(PINNED_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return new Set(Array.isArray(parsed) ? parsed : []);
  } catch {
    return new Set();
  }
}

export default function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const [sessions, setSessions] = useState<SessionUsage[]>([]);
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [dataLoaded, setDataLoaded] = useState(false);
  const [pinnedIds, setPinnedIds] = useState<Set<string>>(() => loadPinnedIds());
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
      section: '跳转',
      icon: SquareStack,
      run: () => navigate(path),
    }));
    const groupItems: PaletteItem[] = availableGroups.map(group => ({
      id: `group:${group}`,
      label: `切换到 ${group}`,
      hint: group === currentGroup ? '当前资源组' : '资源组',
      section: '资源组',
      icon: SquareStack,
      run: () => setCurrentGroup(group),
    }));
    const workspaceItems: PaletteItem[] = projects
      .filter(project => project.path.trim())
      .map(project => ({
        id: `workspace:${project.path}`,
        pinKey: `workspace:${project.path}`,
        label: project.path.split(/[\\/]/).filter(Boolean).pop() || project.path,
        hint: project.path,
        section: '工作区',
        icon: FolderGit2,
        run: () => {
          // Switching workspaces is a global scope change, not navigation:
          // stay on the current page (the old forced jump to /agent/web bound
          // "change workspace" to "go to the chat page" for no reason).
          setSelectedWorkspace(project.path);
        },
      }));
    const sessionItems: PaletteItem[] = sessions.map(session => ({
      id: `session:${session.target}:${session.sessionId}`,
      label: session.projectPath.split(/[\\/]/).filter(Boolean).pop() || session.sessionId,
      hint: `${session.target} 会话 · ${session.projectPath}`,
      section: '会话',
      icon: MessageSquare,
      run: () => navigate(buildSessionLink(session.target, session.sessionId, session.projectPath || '')),
    }));
    const taskItems: PaletteItem[] = tasks.map(task => ({
      id: `task:${task.name}`,
      pinKey: `task:${task.name}`,
      label: task.title || task.name,
      hint: task.description || `任务 · ${task.name}`,
      section: '任务',
      icon: ListChecks,
      run: () => navigate(`/automations/tasks?task=${encodeURIComponent(task.name)}`),
    }));
    // Re-derived from the live workspace/task items (not stored separately)
    // so a pinned entry's label/hint never goes stale after a rename. The
    // clone gets its own `id` for React's list key but keeps the same
    // `pinKey` so unpinning from either copy stays in sync.
    const pinnedItems: PaletteItem[] = [...workspaceItems, ...taskItems]
      .filter(item => item.pinKey && pinnedIds.has(item.pinKey))
      .map(item => ({ ...item, id: `pinned:${item.id}`, section: '已固定' as const }));
    return [...pinnedItems, ...navItems, ...workspaceItems, ...sessionItems, ...taskItems, ...groupItems];
  }, [navigate, availableGroups, currentGroup, setCurrentGroup, projects, setSelectedWorkspace, sessions, tasks, pinnedIds]);

  const togglePinned = (pinKey: string, event: ReactMouseEvent) => {
    event.stopPropagation();
    setPinnedIds(prev => {
      const next = new Set(prev);
      if (next.has(pinKey)) next.delete(pinKey);
      else next.add(pinKey);
      localStorage.setItem(PINNED_STORAGE_KEY, JSON.stringify(Array.from(next)));
      return next;
    });
  };

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
        aria-label="打开命令面板"
        title="搜索 (Ctrl/Cmd+K)"
        className="flex items-center gap-1.5 rounded-xl border border-slate-100 bg-white/50 px-3 py-2 text-slate-500 shadow-sm backdrop-blur-md transition-colors hover:bg-white hover:text-slate-800"
      >
        <Search size={16} />
        <kbd className="hidden rounded border border-slate-200 px-1.5 py-0.5 text-[10px] text-slate-400 sm:inline">
          {navigator.platform.toLowerCase().includes('mac') ? '⌘K' : 'Ctrl K'}
        </kbd>
      </button>

      {open && (
        <Modal
          onClose={() => setOpen(false)}
          ariaLabel="命令面板"
          testId="command-palette"
          overlayClassName="pt-[15vh]"
          panelClassName="max-w-lg overflow-hidden"
        >
          <div className="flex items-center gap-2 border-b border-slate-100 px-4 py-3">
            <Search size={16} className="shrink-0 text-slate-400" />
            <input
              ref={inputRef}
              value={query}
              onChange={event => setQuery(event.target.value)}
              onKeyDown={handleInputKeyDown}
              placeholder="跳转到页面、会话、任务、工作区…"
              aria-label="命令面板搜索"
              className="w-full bg-transparent text-sm text-slate-800 outline-none placeholder:text-slate-400"
            />
            <kbd className="hidden shrink-0 rounded border border-slate-200 px-1.5 py-0.5 text-[10px] text-slate-400 sm:inline">
              Esc
            </kbd>
          </div>
          <ul className="max-h-80 overflow-y-auto py-2" role="listbox" aria-label="命令面板结果">
            {filtered.length === 0 && (
              <li className="px-4 py-6 text-center text-sm text-slate-400">没有匹配项</li>
            )}
            {filtered.map((item, index) => {
              const pinned = !!item.pinKey && pinnedIds.has(item.pinKey);
              return (
                <li
                  key={item.id}
                  role="option"
                  aria-selected={index === activeIndex}
                  className={`flex items-center gap-1 ${index === activeIndex ? 'bg-primary/10' : ''}`}
                >
                  <button
                    type="button"
                    onMouseEnter={() => setActiveIndex(index)}
                    onClick={() => runItem(item)}
                    className={`flex flex-1 min-w-0 items-center justify-between gap-3 px-4 py-2 text-left text-sm transition-colors ${
                      index === activeIndex ? 'text-primary' : 'text-slate-600 hover:bg-slate-50'
                    }`}
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      <item.icon size={14} className="shrink-0 opacity-60" />
                      <span className="truncate font-medium">{item.label}</span>
                      <span className="shrink-0 text-[10px] uppercase tracking-wide text-slate-400">{item.section}</span>
                    </span>
                    <span className="shrink-0 truncate text-xs text-slate-400 max-w-[45%]">{item.hint}</span>
                  </button>
                  {item.pinKey && (
                    <button
                      type="button"
                      onClick={event => togglePinned(item.pinKey!, event)}
                      aria-label={pinned ? `取消固定 ${item.label}` : `固定 ${item.label}`}
                      title={pinned ? '取消固定' : '固定'}
                      className={`shrink-0 p-2 mr-1 rounded-lg transition-colors ${
                        pinned ? 'text-primary hover:bg-primary/10' : 'text-slate-300 hover:text-slate-500 hover:bg-slate-50'
                      }`}
                    >
                      {pinned ? <Pin size={14} className="fill-current" /> : <PinOff size={14} />}
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        </Modal>
      )}
    </>
  );
}
