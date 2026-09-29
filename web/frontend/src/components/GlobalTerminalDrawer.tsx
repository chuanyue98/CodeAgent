import { useState, useRef, useEffect, useLayoutEffect, type CSSProperties } from 'react';
import { useLocation } from 'react-router';
import {
  Terminal, Plus, X, Maximize2, Minimize2, ChevronDown, ChevronUp, Zap, Loader2,
  ZoomIn, ZoomOut, Copy, Check, Expand, Shrink, MoreHorizontal,
} from 'lucide-react';
import { useTerminal } from '../context/TerminalContext';
import BrowserTerminal from './BrowserTerminal';
import SmartHandoffBanner from './SmartHandoffBanner';
import { useT } from '../i18n/context';
import { AGENT_ENGINES, findEngine } from './terminalEngines';
import { convertAndLaunchSession } from '../api/audit';

interface Box { top: number; left: number; width: number; height: number }

/**
 * Viewport box of `el`, kept current. ResizeObserver misses pure moves, so
 * the entrance animations and the nav's width transition re-measure too.
 */
function useElementBox(el: HTMLElement | null): Box | null {
  const [box, setBox] = useState<Box | null>(null);
  useLayoutEffect(() => {
    if (!el) return;
    const update = () => {
      const r = el.getBoundingClientRect();
      setBox(prev => (
        prev && prev.top === r.top && prev.left === r.left
          && prev.width === r.width && prev.height === r.height
      ) ? prev : { top: r.top, left: r.left, width: r.width, height: r.height });
    };
    update();
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(update);
    observer?.observe(el);
    window.addEventListener('resize', update);
    document.addEventListener('animationend', update, true);
    document.addEventListener('transitionend', update, true);
    return () => {
      observer?.disconnect();
      window.removeEventListener('resize', update);
      document.removeEventListener('animationend', update, true);
      document.removeEventListener('transitionend', update, true);
    };
  }, [el]);
  return el ? box : null;
}

export default function GlobalTerminalDrawer() {
  const {
    tabs,
    activeTabId,
    rateLimitedTabIds,
    isDrawerOpen,
    isMaximized,
    fontSize,
    copyOnSelect,
    zenMode,
    terminalSlot,
    openTab,
    closeTab,
    setActiveTabId,
    toggleDrawer,
    openDrawer,
    closeDrawer,
    toggleMaximize,
    increaseFontSize,
    decreaseFontSize,
    resetFontSize,
    toggleCopyOnSelect,
    toggleZenMode,
    markRateLimited,
    clearRateLimited,
  } = useTerminal();

  const t = useT();

  const [handoffLoading, setHandoffLoading] = useState<string | null>(null);
  const [handoffError, setHandoffError] = useState<string | null>(null);
  const [showHandoffMenu, setShowHandoffMenu] = useState(false);
  const handoffMenuRef = useRef<HTMLDivElement | null>(null);
  const [showMoreMenu, setShowMoreMenu] = useState(false);
  const moreMenuRef = useRef<HTMLDivElement | null>(null);
  const { pathname } = useLocation();
  const onTerminalPage = pathname === '/agent/terminal';
  const activeTab = tabs.find(tab => tab.id === activeTabId);
  // On the terminal page the session is the page: it fills the slot LaunchPad
  // leaves for it. Everywhere else it is the bottom drawer.
  const docked = onTerminalPage && Boolean(activeTab) && Boolean(terminalSlot);
  const slotBox = useElementBox(docked ? terminalSlot : null);

  // Leaving the terminal page must not drop the session on top of the next
  // page as a 60vh drawer; it goes to the dock bar instead.
  const wasOnTerminalPage = useRef(onTerminalPage);
  useEffect(() => {
    if (wasOnTerminalPage.current && !onTerminalPage) closeDrawer();
    wasOnTerminalPage.current = onTerminalPage;
  }, [onTerminalPage, closeDrawer]);

  useEffect(() => {
    if (!showMoreMenu) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (moreMenuRef.current && !moreMenuRef.current.contains(e.target as Node)) {
        setShowMoreMenu(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showMoreMenu]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (handoffMenuRef.current && !handoffMenuRef.current.contains(e.target as Node)) {
        setShowHandoffMenu(false);
      }
    };
    if (showHandoffMenu) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [showHandoffMenu]);

  if (tabs.length === 0) return null;

  const isAgentEngine = Boolean(activeTab && AGENT_ENGINES.some(e => e.id === activeTab.engine));

  const handleHandoff = async (targetEngineId: string) => {
    if (!activeTab) return;
    setHandoffLoading(targetEngineId);
    setHandoffError(null);
    try {
      const result = await convertAndLaunchSession({
        sourceEngine: activeTab.engine,
        sessionId: activeTab.sessionId,
        targetEngine: targetEngineId,
        projectPath: activeTab.cwd,
      });
      closeTab(activeTab.id);
      openTab(result.engine, result.project, result.sessionId);
    } catch (err) {
      console.error(err);
      setHandoffError(err instanceof Error ? err.message : String(err));
    } finally {
      setHandoffLoading(null);
      setShowHandoffMenu(false);
    }
  };

  let frame: string;
  let frameStyle: CSSProperties | undefined;
  // Whether the active terminal is actually on screen, measured. Until it is,
  // its engine isn't started: it would start at a size nobody sees.
  let showing = true;
  if (zenMode && (docked || isDrawerOpen)) {
    frame = 'fixed inset-0 z-[100] h-screen';
  } else if (docked) {
    frame = 'fixed z-40 overflow-hidden';
    frameStyle = slotBox ?? { visibility: 'hidden' };
    showing = Boolean(slotBox);
  } else if (!isDrawerOpen || onTerminalPage) {
    showing = false;
    // Still rendered: every tab's terminal must stay mounted to keep its PTY.
    frame = 'fixed bottom-0 left-0 right-0 invisible h-0 overflow-hidden';
  } else {
    frame = `fixed bottom-0 left-0 right-0 z-50 shadow-[0_-10px_40px_rgba(0,0,0,0.1)] transition-all duration-300 ${
      isMaximized ? 'top-0' : 'h-[60vh] min-h-[300px]'
    }`;
  }

  const handleDismissBanner = () => {
    if (activeTabId) clearRateLimited(activeTabId);
  };

  return (
    <>
      {/* Minimized state dock bar */}
      <div 
        className={`fixed bottom-0 left-0 right-0 z-50 flex items-center justify-between border-t border-slate-200 bg-white/95 px-4 py-2 shadow-[0_-4px_10px_rgba(0,0,0,0.05)] backdrop-blur transition-transform hover:bg-slate-50 cursor-pointer ${isDrawerOpen || onTerminalPage ? 'hidden' : ''}`}
        onClick={openDrawer}
        data-testid="dock-bar"
      >
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 text-slate-500">
            <Terminal size={16} />
            <span className="text-xs font-semibold">{tabs.length} {t('launch.tabs')}</span>
          </div>
          <div className="flex gap-2">
            {tabs.map(tab => {
              const engine = findEngine(tab.engine);
              const isRateLimited = rateLimitedTabIds.has(tab.id);
              return (
                <div key={tab.id} className="flex items-center gap-1.5 rounded-full border border-slate-200 bg-slate-100 px-3 py-1 text-xs">
                  <span className={`h-2 w-2 rounded-full ${isRateLimited ? 'bg-amber-400' : 'bg-green-500'}`} />
                  <span className="font-medium text-slate-700">{engine?.name || tab.engine}</span>
                </div>
              );
            })}
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="hidden rounded bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-400 sm:inline-block">
            Ctrl+`
          </span>
          <ChevronUp size={16} className="text-slate-400" />
        </div>
      </div>

      {/* Expanded State */}
      <div 
        className={`flex flex-col bg-card ${frame}`}
        style={frameStyle}
        data-testid="drawer-expanded"
        onTransitionEnd={() => {
          window.dispatchEvent(new Event('resize'));
        }}
      >
        <div className="flex shrink-0 items-stretch justify-between border-b border-border bg-card">
          <div className="flex min-w-0 items-stretch overflow-x-auto custom-scrollbar">
            {tabs.map(tab => {
              const engine = findEngine(tab.engine);
              const isActive = tab.id === activeTabId;
              const isRateLimited = rateLimitedTabIds.has(tab.id);
              return (
                <div
                  key={tab.id}
                  role="tab"
                  aria-selected={isActive}
                  onClick={() => setActiveTabId(tab.id)}
                  className={`group relative flex min-w-[120px] max-w-[220px] cursor-pointer items-center gap-2 border-r border-border px-4 text-sm font-medium transition-colors ${
                    isActive ? 'bg-term text-term-fg' : 'text-muted-foreground hover:bg-muted/60 hover:text-foreground'
                  }`}
                >
                  {isActive && <span aria-hidden className={`absolute inset-x-0 top-0 h-0.5 ${engine?.dot ?? 'bg-primary'}`} />}
                  <div className={`h-2 w-2 shrink-0 rounded-full ${isRateLimited ? 'bg-warn' : (engine?.dot ?? 'bg-slate-400')}`} />
                  <span className="truncate">{engine?.name || tab.engine}</span>
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); closeTab(tab.id); }}
                    className="ml-auto opacity-0 transition-opacity group-hover:opacity-100 hover:bg-slate-200 p-0.5 rounded"
                    aria-label="Close terminal"
                  >
                    <X size={14} />
                  </button>
                </div>
              );
            })}
            <button
              onClick={() => setActiveTabId(null)}
              className="flex w-10 items-center justify-center text-muted-foreground hover:bg-muted/60 hover:text-foreground"
              title="Switch to Launcher"
              aria-label="New terminal"
            >
              <Plus size={16} />
            </button>
          </div>

          <div className="ml-4 flex shrink-0 items-center gap-1.5 pr-2">
            {isAgentEngine && activeTab && (
              <div ref={handoffMenuRef} className="relative">
                <button
                  type="button"
                  data-testid="handoff-button"
                  disabled={Boolean(handoffLoading)}
                  onClick={() => setShowHandoffMenu(prev => !prev)}
                  title={t('launch.handoffTitle')}
                  aria-label={t('launch.handoffTitle')}
                  className="flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 transition-colors mr-1 disabled:opacity-50"
                >
                  {handoffLoading ? (
                    <Loader2 size={13} className="animate-spin text-amber-500" />
                  ) : (
                    <Zap size={13} className="text-amber-500" />
                  )}
                  <span>{t('launch.handoff')}</span>
                  <ChevronDown
                    size={12}
                    className={showHandoffMenu ? 'rotate-180 transition-transform' : 'transition-transform'}
                  />
                </button>
                {showHandoffMenu && (
                  <div
                    data-testid="handoff-menu"
                    className="absolute right-0 top-full z-50 mt-1 min-w-[160px] rounded-xl border border-slate-200 bg-white p-1 shadow-lg backdrop-blur"
                  >
                    <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                      {t('launch.handoffTitle')}
                    </div>
                    {AGENT_ENGINES.filter(e => e.id !== activeTab.engine).map(target => {
                      const isTargetLoading = handoffLoading === target.id;
                      return (
                        <button
                          key={target.id}
                          type="button"
                          disabled={Boolean(handoffLoading)}
                          onClick={() => void handleHandoff(target.id)}
                          className="flex w-full items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-100 disabled:opacity-50 transition-colors"
                        >
                          <span className="flex items-center gap-2">
                            <span className={`h-2 w-2 rounded-full ${target.dot}`} />
                            <span>{target.nameKey ? t(target.nameKey) : target.name}</span>
                          </span>
                          {isTargetLoading && <Loader2 size={12} className="animate-spin text-amber-500" />}
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {/* Settings you change once and forget; kept off the bar so the
                session's own title and actions are what it shows. */}
            <div ref={moreMenuRef} className="relative">
              <button
                type="button"
                data-testid="terminal-more-button"
                onClick={() => setShowMoreMenu(prev => !prev)}
                className="rounded p-1.5 text-slate-400 hover:bg-slate-200 hover:text-slate-600 transition-colors"
                title={t('terminal.more')}
                aria-label={t('terminal.more')}
                aria-expanded={showMoreMenu}
              >
                <MoreHorizontal size={16} />
              </button>
              {showMoreMenu && (
                <div
                  data-testid="terminal-more-menu"
                  className="absolute right-0 top-full z-50 mt-1 w-64 space-y-1 rounded-xl border border-slate-200 bg-white p-2 text-xs text-slate-600 shadow-xl"
                >
                  <div className="flex items-center justify-between px-1 py-1">
                    <span>{t('terminal.fontSize')}</span>
                    <div className="flex items-center rounded-lg border border-slate-200 bg-white p-0.5 text-slate-500">
                      <button
                        type="button"
                        data-testid="terminal-zoom-out"
                        onClick={decreaseFontSize}
                        disabled={fontSize <= 10}
                        className="rounded p-1 hover:bg-slate-100 hover:text-slate-700 disabled:opacity-30 transition-colors"
                        title={t('terminal.zoomOut')}
                        aria-label={t('terminal.zoomOut')}
                      >
                        <ZoomOut size={13} />
                      </button>
                      <button
                        type="button"
                        data-testid="terminal-font-size-btn"
                        onClick={resetFontSize}
                        className="px-1 text-[11px] font-mono font-medium hover:text-primary transition-colors"
                        title={t('terminal.resetZoom')}
                        aria-label={t('terminal.resetZoom')}
                      >
                        {fontSize}px
                      </button>
                      <button
                        type="button"
                        data-testid="terminal-zoom-in"
                        onClick={increaseFontSize}
                        disabled={fontSize >= 24}
                        className="rounded p-1 hover:bg-slate-100 hover:text-slate-700 disabled:opacity-30 transition-colors"
                        title={t('terminal.zoomIn')}
                        aria-label={t('terminal.zoomIn')}
                      >
                        <ZoomIn size={13} />
                      </button>
                    </div>
                  </div>
                  <button
                    type="button"
                    data-testid="copy-on-select-toggle"
                    onClick={toggleCopyOnSelect}
                    aria-pressed={copyOnSelect}
                    className="flex w-full items-center justify-between rounded-lg px-1 py-1.5 text-left hover:bg-slate-100"
                    title={copyOnSelect ? t('terminal.copyOnSelectEnabled') : t('terminal.copyOnSelectDisabled')}
                  >
                    <span>{t('terminal.copyOnSelect')}</span>
                    {copyOnSelect ? <Check size={13} className="text-emerald-600" /> : <Copy size={13} className="text-slate-400" />}
                  </button>
                  <button
                    type="button"
                    data-testid="zen-mode-toggle"
                    onClick={() => { toggleZenMode(); setShowMoreMenu(false); }}
                    className="flex w-full items-center justify-between rounded-lg px-1 py-1.5 text-left hover:bg-slate-100"
                  >
                    <span>{zenMode ? t('terminal.zenModeExit') : t('terminal.zenMode')}</span>
                    {zenMode ? <Shrink size={13} /> : <Expand size={13} />}
                  </button>
                  <div className="border-t border-slate-100 px-1 pt-2">
                    <div className="mb-1.5 font-semibold text-slate-800">{t('terminal.shortcuts')}</div>
                    <ul className="space-y-1 text-[11px] text-slate-500">
                      <li className="flex justify-between"><span>{t('terminal.shortcutCopy')}</span><kbd className="rounded bg-slate-100 px-1 font-mono text-[10px]">Ctrl+C</kbd></li>
                      <li className="flex justify-between"><span>{t('terminal.shortcutPaste')}</span><kbd className="rounded bg-slate-100 px-1 font-mono text-[10px]">Ctrl+Shift+V</kbd></li>
                      <li className="flex justify-between"><span>{t('terminal.shortcutZoom')}</span><kbd className="rounded bg-slate-100 px-1 font-mono text-[10px]">Ctrl + / - / 0</kbd></li>
                      {!docked && (
                        <li className="flex justify-between"><span>{t('terminal.shortcutDrawer')}</span><kbd className="rounded bg-slate-100 px-1 font-mono text-[10px]">Ctrl+`</kbd></li>
                      )}
                    </ul>
                  </div>
                </div>
              )}
            </div>

            {/* Sizing a drawer means nothing once the session is the page. */}
            {!docked && (
              <>
                <button
                  onClick={toggleMaximize}
                  className="rounded p-1.5 text-slate-400 hover:bg-slate-200 hover:text-slate-600"
                  title="Maximize"
                  aria-label="Maximize"
                >
                  {isMaximized ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
                </button>
                <button
                  onClick={toggleDrawer}
                  className="rounded p-1.5 text-slate-400 hover:bg-slate-200 hover:text-slate-600"
                  title="Minimize Drawer"
                  aria-label="Minimize Drawer"
                >
                  <ChevronDown size={16} />
                </button>
              </>
            )}
          </div>
        </div>

        {handoffError && (
          <div className="flex items-center justify-between border-b border-red-200 bg-red-50 p-2 text-xs text-red-700">
            <span>{t('launch.handoffFailed', { error: handoffError }) || handoffError}</span>
            <button onClick={() => setHandoffError(null)} className="p-0.5 text-red-500 hover:text-red-700">
              <X size={14} />
            </button>
          </div>
        )}

        {activeTabId && rateLimitedTabIds.has(activeTabId) && activeTab && (
          <div className="p-2 border-b border-amber-200 bg-amber-50">
            <SmartHandoffBanner
              activeEngine={activeTab.engine}
              onHandoff={handleHandoff}
              onDismiss={handleDismissBanner}
              loadingEngine={handoffLoading}
            />
          </div>
        )}

        <div className="relative flex-1 min-h-0 bg-term">
          {tabs.map(tab => (
            <div
              key={tab.id}
              className={tab.id === activeTabId ? 'absolute inset-0 flex flex-col' : 'hidden'}
            >
              <BrowserTerminal
                engine={tab.engine}
                cwd={tab.cwd}
                sessionId={tab.sessionId}
                attachId={tab.attachId}
                tabKey={tab.id}
                initialPrompt={tab.prompt}
                active={showing && tab.id === activeTabId}
                fontSize={fontSize}
                copyOnSelect={copyOnSelect}
                // 引擎自己退出时不关标签页：BrowserTerminal 会就地显示退出码
                // 和"重新开始"，用户还看得见最后那屏输出。这里挂 closeTab 会
                // 立刻卸载终端、退回引擎选择器，退出原因和尾屏一起消失。
                // 关标签页是用户动作，归上面的关闭按钮管。
                onTerminalEvent={(event) => {
                  if (event === 'rate_limit') {
                    markRateLimited(tab.id);
                  }
                }}
              />
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
