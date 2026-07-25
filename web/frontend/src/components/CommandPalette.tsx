import { useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';
import { useNavigate } from 'react-router';
import { Search, SquareStack } from 'lucide-react';
import { useProject } from '../context/ProjectContext';
import { PAGE_LABELS } from '../navigation';

interface PaletteItem {
  id: string;
  label: string;
  hint: string;
  section: 'Navigate' | 'Project';
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
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const { availableGroups, currentGroup, setCurrentGroup } = useProject();

  const items = useMemo<PaletteItem[]>(() => {
    const navItems: PaletteItem[] = Object.entries(PAGE_LABELS).map(([path, label]) => ({
      id: `nav:${path}`,
      label,
      hint: path,
      section: 'Navigate',
      run: () => navigate(path),
    }));
    const groupItems: PaletteItem[] = availableGroups.map(group => ({
      id: `group:${group}`,
      label: `Switch to ${group}`,
      hint: group === currentGroup ? 'current resource group' : 'resource group',
      section: 'Project',
      run: () => setCurrentGroup(group),
    }));
    return [...navItems, ...groupItems];
  }, [navigate, availableGroups, currentGroup, setCurrentGroup]);

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
                placeholder="Go to a page, resource group…"
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
                      <SquareStack size={14} className="shrink-0 opacity-60" />
                      <span className="truncate font-medium">{item.label}</span>
                    </span>
                    <span className="shrink-0 truncate text-xs text-slate-400">{item.hint}</span>
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
