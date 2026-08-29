import { useEffect, useMemo, useRef, useState } from 'react';
import { FolderGit2, ChevronDown, CornerDownLeft } from 'lucide-react';
import { Link } from 'react-router';
import { useProject } from '../context/ProjectContext';
import { useT } from '../i18n/context';
import { workspaceLabel } from '../utils/workspaceFormat';

interface Option {
  path: string;
  group?: string;
  /** Typed in rather than picked from the registry. */
  custom: boolean;
}

/**
 * Header-level switcher for the shared workspace selection. The workspace
 * used to be visible only inside each page's own dropdown (Agent, Terminal,
 * Tasks, Schedules), so the rest of the app gave no hint of "which project
 * am I on right now" — this surfaces it globally, next to the group chip.
 *
 * It also owns the "any existing directory" case. The Local Terminal page
 * carried a second workspace field for that, which meant two controls on one
 * screen writing the same selection, and only one of them able to accept a
 * path the registry had never heard of.
 */
export default function WorkspaceSwitcher() {
  const t = useT();
  const {
    validProjects,
    customWorkspaces,
    selectedWorkspace,
    setSelectedWorkspace,
    availableGroups,
    currentGroup,
    setCurrentGroup,
  } = useProject();
  const [open, setOpen] = useState(false);
  const [focusedIndex, setFocusedIndex] = useState(-1);
  const [draft, setDraft] = useState('');
  const ref = useRef<HTMLDivElement>(null);
  const listboxRef = useRef<HTMLDivElement>(null);

  // Registered first, then directories the user typed in. One flat list so
  // arrow keys walk everything the dropdown offers.
  const options = useMemo<Option[]>(() => {
    const registered = validProjects.map(project => ({
      path: project.path,
      group: project.group,
      custom: false,
    }));
    const registeredPaths = new Set(registered.map(option => option.path));
    const custom = customWorkspaces
      .filter(path => !registeredPaths.has(path))
      .map(path => ({ path, custom: true }));
    return [...registered, ...custom];
  }, [validProjects, customWorkspaces]);

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
      const idx = options.findIndex(option => option.path === selectedWorkspace);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setFocusedIndex(idx >= 0 ? idx : 0);
    } else {
      setFocusedIndex(-1);
      setDraft('');
    }
  }, [open, selectedWorkspace, options]);

  useEffect(() => {
    if (open && focusedIndex >= 0 && listboxRef.current) {
      const option = listboxRef.current.querySelectorAll('[role="option"]')[focusedIndex] as HTMLElement;
      if (option) {
        option.scrollIntoView({ block: 'nearest' });
        option.focus();
      }
    }
  }, [focusedIndex, open]);

  const pick = (path: string) => {
    setSelectedWorkspace(path);
    setOpen(false);
  };

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
        setFocusedIndex((prev) => (prev < options.length - 1 ? prev + 1 : 0));
        break;
      case 'ArrowUp':
        e.preventDefault();
        setFocusedIndex((prev) => (prev > 0 ? prev - 1 : options.length - 1));
        break;
      case 'Enter':
      case ' ':
        e.preventDefault();
        if (focusedIndex >= 0 && focusedIndex < options.length) {
          pick(options[focusedIndex].path);
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
        setFocusedIndex(options.length - 1);
        break;
    }
  };

  const submitDraft = (e: React.FormEvent) => {
    e.preventDefault();
    const path = draft.trim();
    if (!path) return;
    pick(path);
  };

  // A typed path that has not been recorded yet still names the selection —
  // falling back to "none selected" would claim the app is pointed nowhere.
  const currentLabel = selectedWorkspace
    ? workspaceLabel(selectedWorkspace)
    : t('workspaceSwitcher.none');
  const customOffset = validProjects.length;

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        onKeyDown={handleKeyDown}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={t('workspaceSwitcher.current', { name: currentLabel })}
        title={selectedWorkspace || t('workspaceSwitcher.pick')}
        className="flex max-w-56 items-center gap-2 px-3 md:px-4 py-2 bg-white/50 backdrop-blur-md border border-slate-100 rounded-xl hover:bg-white transition-colors shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
      >
        <FolderGit2 size={16} className="text-primary shrink-0" />
        <span className="truncate text-sm font-semibold">
          <span className="hidden text-slate-400 lg:inline">{t('workspaceSwitcher.prefix')}</span>
          {currentLabel}
        </span>
        <ChevronDown size={14} className={`text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="absolute right-0 z-50 mt-2 w-72 max-w-[calc(100vw-1rem)] overflow-hidden rounded-xl border border-slate-100 bg-white shadow-xl">
          <div role="listbox" ref={listboxRef} className="max-h-64 overflow-y-auto p-2" onKeyDown={handleKeyDown}>
            {validProjects.length > 0 && (
              <div className="px-2 pb-1 pt-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                {t('workspaceSwitcher.registered')}
              </div>
            )}
            {options.map((option, index) => (
              <div key={option.path}>
                {option.custom && index === customOffset && (
                  <div className="mt-1 border-t border-slate-100 px-2 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                    {t('workspaceSwitcher.recent')}
                  </div>
                )}
                <button
                  role="option"
                  aria-selected={option.path === selectedWorkspace}
                  tabIndex={focusedIndex === index ? 0 : -1}
                  onClick={() => pick(option.path)}
                  title={option.path}
                  className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                    option.path === selectedWorkspace
                      ? 'bg-primary/10 text-primary font-bold'
                      : focusedIndex === index
                      ? 'bg-slate-100 text-slate-900'
                      : 'hover:bg-slate-50 text-slate-600'
                  }`}
                >
                  <span className="block truncate">{workspaceLabel(option.path)}</span>
                  <span className="block truncate text-[10px] font-normal text-slate-400">{option.path}</span>
                </button>
              </div>
            ))}
          </div>

          {/* Any existing directory on the host counts, so the registry is a
              list of suggestions rather than the whole world. Without this the
              switcher was a dead end on a fresh install — nothing registered
              meant nothing to pick, and every page that reads the selection
              stayed empty. */}
          <form onSubmit={submitDraft} className="border-t border-slate-100 p-2">
            <label
              htmlFor="workspace-custom-path"
              className="block px-1 pb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400"
            >
              {t('workspaceSwitcher.customLabel')}
            </label>
            <div className="flex items-center gap-1">
              <input
                id="workspace-custom-path"
                value={draft}
                onChange={event => setDraft(event.target.value)}
                onKeyDown={event => {
                  if (event.key === 'Escape') {
                    event.preventDefault();
                    setOpen(false);
                  }
                }}
                placeholder={t('workspaceSwitcher.customPlaceholder')}
                spellCheck={false}
                className="min-w-0 flex-1 rounded-lg border border-slate-200 px-2 py-1.5 font-mono text-xs focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
              />
              <button
                type="submit"
                disabled={!draft.trim()}
                aria-label={t('workspaceSwitcher.customSubmit')}
                title={t('workspaceSwitcher.customSubmit')}
                className="shrink-0 rounded-lg p-1.5 text-primary transition-colors hover:bg-primary/10 disabled:opacity-40"
              >
                <CornerDownLeft size={14} />
              </button>
            </div>
          </form>

          {/* The resource group used to be its own header chip, equal in weight
              to the workspace next to it. It is a property *of* the workspace —
              setSelectedWorkspace already moves it — so it belongs inside this
              menu, where the rule that ties them is visible. Changing it by
              hand stays possible here and in the command palette. */}
          <div className="space-y-1.5 border-t border-slate-100 bg-slate-50/70 px-4 py-3">
            <label
              htmlFor="workspace-group"
              className="block text-[10px] font-semibold uppercase tracking-wider text-slate-400"
            >
              {t('groupSwitcher.heading')}
            </label>
            <select
              id="workspace-group"
              data-testid="group-switcher"
              value={currentGroup}
              onChange={event => setCurrentGroup(event.target.value)}
              onKeyDown={event => {
                if (event.key === 'Escape') setOpen(false);
              }}
              className="w-full rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs font-medium text-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
            >
              {availableGroups.map(group => (
                <option key={group} value={group}>{group}</option>
              ))}
            </select>
            <p className="text-[11px] text-slate-500">
              {t('workspaceSwitcher.groupNote')}{' '}
              <Link to="/settings/workspace" className="text-primary hover:underline">{t('workspaceSwitcher.manage')}</Link>
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
