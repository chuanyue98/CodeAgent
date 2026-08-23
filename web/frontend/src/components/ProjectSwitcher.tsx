import { useState, useRef, useEffect } from 'react';
import { useProject } from '../context/ProjectContext';
import { useT } from '../i18n/context';
import { Layers, ChevronDown } from 'lucide-react';

export default function ProjectSwitcher() {
  const t = useT();
  const { currentGroup, setCurrentGroup, availableGroups, groups } = useProject();
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

  // When opening, focus the current group
  useEffect(() => {
    if (open) {
      const idx = availableGroups.indexOf(currentGroup);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setFocusedIndex(idx >= 0 ? idx : 0);
    } else {
      setFocusedIndex(-1);
    }
  }, [open, currentGroup, availableGroups]);

  // Scroll focused option into view and move browser focus
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
          prev < availableGroups.length - 1 ? prev + 1 : 0
        );
        break;
      case 'ArrowUp':
        e.preventDefault();
        setFocusedIndex((prev) =>
          prev > 0 ? prev - 1 : availableGroups.length - 1
        );
        break;
      case 'Enter':
      case ' ':
        e.preventDefault();
        if (focusedIndex >= 0 && focusedIndex < availableGroups.length) {
          setCurrentGroup(availableGroups[focusedIndex]);
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
        setFocusedIndex(availableGroups.length - 1);
        break;
    }
  };

  const current = groups[currentGroup];
  const resourceCount = (current?.skills?.length ?? 0)
    + (current?.prompts?.length ?? 0)
    + (current?.hooks?.length ?? 0)
    + (current?.plugins?.length ?? 0);

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        onKeyDown={handleKeyDown}
        data-testid="group-switcher"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={t('groupSwitcher.label', { group: currentGroup })}
        title={t('groupSwitcher.label', { group: currentGroup })}
        className="flex max-w-64 items-center gap-2 px-3 md:px-4 py-2 bg-white/50 backdrop-blur-md border border-slate-100 rounded-xl hover:bg-white transition-colors shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
      >
        <Layers size={16} className="text-primary shrink-0" />
        {/* The "Group · " prefix used to eat the budget and truncate the one
            part that matters ("Group · codea…"). The name wins; the label
            drops out first on narrow headers. */}
        <span className="truncate text-sm font-semibold">
          <span className="hidden text-slate-400 lg:inline">{t('groupSwitcher.prefix')}</span>{currentGroup}
        </span>
        <ChevronDown size={14} className={`text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="absolute right-0 z-50 mt-2 w-56 max-w-[calc(100vw-1rem)] overflow-hidden rounded-xl border border-slate-100 bg-white shadow-xl">
          <div className="px-4 pb-1 pt-3 text-[10px] font-semibold uppercase tracking-wider text-slate-400">{t('groupSwitcher.heading')}</div>
          <div role="listbox" ref={listboxRef} className="p-2 pt-1 max-h-64 overflow-y-auto" onKeyDown={handleKeyDown}>
            {availableGroups.map((group, index) => (
              <button
                key={group}
                role="option"
                aria-selected={currentGroup === group}
                tabIndex={focusedIndex === index ? 0 : -1}
                onClick={() => { setCurrentGroup(group); setOpen(false); }}
                className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                  currentGroup === group
                    ? 'bg-primary/10 text-primary font-bold'
                    : focusedIndex === index
                    ? 'bg-slate-100 text-slate-900'
                    : 'hover:bg-slate-50 text-slate-600'
                }`}
              >
                {group}
              </button>
            ))}
          </div>
          <div className="border-t border-slate-100 bg-slate-50/70 px-4 py-2 text-[11px] text-slate-500">
            {t('groupSwitcher.resourceCount', { count: resourceCount })}
          </div>
        </div>
      )}
    </div>
  );
}
