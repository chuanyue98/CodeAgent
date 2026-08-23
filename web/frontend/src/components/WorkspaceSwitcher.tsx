import { useEffect, useRef, useState } from 'react';
import { FolderGit2, ChevronDown } from 'lucide-react';
import { Link } from 'react-router';
import { useProject } from '../context/ProjectContext';
import { useT } from '../i18n/context';
import { workspaceLabel } from '../utils/agentWorkspaceHelpers';

/**
 * Header-level switcher for the shared workspace selection. The workspace
 * used to be visible only inside each page's own dropdown (Agent, Terminal,
 * Tasks, Schedules), so the rest of the app gave no hint of "which project
 * am I on right now" — this surfaces it globally, next to the group chip.
 */
export default function WorkspaceSwitcher() {
  const t = useT();
  const { validProjects, selectedWorkspace, setSelectedWorkspace } = useProject();
  const [open, setOpen] = useState(false);
  const [focusedIndex, setFocusedIndex] = useState(-1);
  const ref = useRef<HTMLDivElement>(null);
  const listboxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useEffect(() => {
    if (open) {
      const idx = validProjects.findIndex(project => project.path === selectedWorkspace);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setFocusedIndex(idx >= 0 ? idx : 0);
    } else {
      setFocusedIndex(-1);
    }
  }, [open, selectedWorkspace, validProjects]);

  useEffect(() => {
    if (open && focusedIndex >= 0 && listboxRef.current) {
      const option = listboxRef.current.querySelectorAll('[role="option"]')[focusedIndex] as HTMLElement;
      if (option) {
        option.scrollIntoView({ block: 'nearest' });
        option.focus();
      }
    }
  }, [focusedIndex, open]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!open) {
      if (e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        setOpen(true);
      }
      return;
    }

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setFocusedIndex((prev) =>
          prev < validProjects.length - 1 ? prev + 1 : 0
        );
        break;
      case 'ArrowUp':
        e.preventDefault();
        setFocusedIndex((prev) =>
          prev > 0 ? prev - 1 : validProjects.length - 1
        );
        break;
      case 'Enter':
      case ' ':
        e.preventDefault();
        if (focusedIndex >= 0 && focusedIndex < validProjects.length) {
          setSelectedWorkspace(validProjects[focusedIndex].path);
          setOpen(false);
        }
        break;
      case 'Escape':
        e.preventDefault();
        setOpen(false);
        break;
      case 'Home':
        e.preventDefault();
        setFocusedIndex(0);
        break;
      case 'End':
        e.preventDefault();
        setFocusedIndex(validProjects.length - 1);
        break;
    }
  };

  const current = validProjects.find(project => project.path === selectedWorkspace);

  // With nothing registered there is nothing to switch between — the Agent
  // and Settings pages carry the "go register something" guidance.
  if (validProjects.length === 0) return null;

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        onKeyDown={handleKeyDown}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={t('workspaceSwitcher.current', {
          name: current ? workspaceLabel(current.path) : t('workspaceSwitcher.none'),
        })}
        title={current?.path || t('workspaceSwitcher.pick')}
        className="flex max-w-56 items-center gap-2 px-3 md:px-4 py-2 bg-white/50 backdrop-blur-md border border-slate-100 rounded-xl hover:bg-white transition-colors shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
      >
        <FolderGit2 size={16} className="text-primary shrink-0" />
        <span className="truncate text-sm font-semibold">
          <span className="hidden text-slate-400 lg:inline">{t('workspaceSwitcher.prefix')}</span>
          {current ? workspaceLabel(current.path) : t('workspaceSwitcher.none')}
        </span>
        <ChevronDown size={14} className={`text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="absolute right-0 z-50 mt-2 w-64 max-w-[calc(100vw-1rem)] overflow-hidden rounded-xl border border-slate-100 bg-white shadow-xl">
          <div className="px-4 pb-1 pt-3 text-[10px] font-semibold uppercase tracking-wider text-slate-400">{t('filters.workspace')}</div>
          <div role="listbox" ref={listboxRef} className="p-2 pt-1 max-h-64 overflow-y-auto" onKeyDown={handleKeyDown}>
            {validProjects.map((project, index) => (
              <button
                key={project.path}
                role="option"
                aria-selected={project.path === selectedWorkspace}
                tabIndex={focusedIndex === index ? 0 : -1}
                onClick={() => { setSelectedWorkspace(project.path); setOpen(false); }}
                title={project.path}
                className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                  project.path === selectedWorkspace
                    ? 'bg-primary/10 text-primary font-bold'
                    : focusedIndex === index
                    ? 'bg-slate-100 text-slate-900'
                    : 'hover:bg-slate-50 text-slate-600'
                }`}
              >
                <span className="block truncate">{workspaceLabel(project.path)}</span>
                <span className="block truncate text-[10px] font-normal text-slate-400">{project.path}</span>
              </button>
            ))}
          </div>
          <div className="border-t border-slate-100 bg-slate-50/70 px-4 py-2 text-[11px] text-slate-500">
            {t('workspaceSwitcher.groupNote', { group: current?.group ?? '—' })}{' '}
            <Link to="/settings/workspace" className="text-primary hover:underline">{t('workspaceSwitcher.manage')}</Link>
          </div>
        </div>
      )}
    </div>
  );
}
