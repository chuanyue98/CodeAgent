import { useState } from 'react';
import { Terminal, Plus, X, Maximize2, Minimize2, ChevronDown, ChevronUp, Zap, Loader2 } from 'lucide-react';
import { useTerminal } from '../context/TerminalContext';
import BrowserTerminal from './BrowserTerminal';
import SmartHandoffBanner from './SmartHandoffBanner';
import { useT } from '../i18n/context';
import { AGENT_ENGINES, findEngine } from './terminalEngines';
import { convertAndLaunchSession } from '../api/audit';

export default function GlobalTerminalDrawer() {
  const {
    tabs,
    activeTabId,
    rateLimitedTabIds,
    isDrawerOpen,
    isMaximized,
    openTab,
    closeTab,
    setActiveTabId,
    toggleDrawer,
    openDrawer,
    toggleMaximize,
    markRateLimited,
    clearRateLimited,
  } = useTerminal();

  const t = useT();

  const [handoffLoading, setHandoffLoading] = useState<string | null>(null);
  const [handoffError, setHandoffError] = useState<string | null>(null);
  const [showHandoffMenu, setShowHandoffMenu] = useState(false);

  if (tabs.length === 0) return null;

  const activeTab = tabs.find(tab => tab.id === activeTabId);

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
      console.log("HANDOFF RESULT", result); openTab(result.engine, result.project, result.sessionId);
    } catch (err) {
      console.error(err); setHandoffError(err instanceof Error ? err.message : String(err));
    } finally {
      setHandoffLoading(null);
      setShowHandoffMenu(false);
    }
  };

  const handleDismissBanner = () => {
    if (activeTabId) clearRateLimited(activeTabId);
  };

  return (
    <>
      {/* Minimized state dock bar */}
      <div 
        className={`fixed bottom-0 left-0 right-0 z-50 flex items-center justify-between border-t border-slate-200 bg-white/95 px-4 py-2 shadow-[0_-4px_10px_rgba(0,0,0,0.05)] backdrop-blur transition-transform hover:bg-slate-50 cursor-pointer ${isDrawerOpen ? 'hidden' : ''}`}
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
        className={`fixed bottom-0 left-0 right-0 z-50 flex flex-col bg-white shadow-[0_-10px_40px_rgba(0,0,0,0.1)] transition-all duration-300 ${!isDrawerOpen ? 'invisible h-0 overflow-hidden' : isMaximized ? 'top-0' : 'h-[60vh] min-h-[300px]'}`}
        data-testid="drawer-expanded"
        onTransitionEnd={() => {
          window.dispatchEvent(new Event('resize'));
        }}
      >
        <div className="flex shrink-0 items-center justify-between border-b border-slate-200 bg-slate-50 px-2 py-1.5">
          <div className="flex min-w-0 items-center gap-1 overflow-x-auto custom-scrollbar">
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
                  className={`group flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm transition-colors cursor-pointer min-w-[120px] max-w-[200px] ${
                    isActive ? 'bg-white font-medium text-slate-800 shadow-sm border border-slate-200' : 'text-slate-600 hover:bg-slate-200/50 hover:text-slate-900 border border-transparent'
                  }`}
                >
                  <div className={`h-2 w-2 shrink-0 rounded-full ${isRateLimited ? 'bg-amber-400' : (isActive ? 'bg-green-500' : 'bg-slate-300')}`} />
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
              className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-200 hover:text-slate-600"
              title="Switch to Launcher"
              aria-label="New terminal"
            >
              <Plus size={16} />
            </button>
          </div>

          <div className="flex items-center gap-1.5 ml-4 shrink-0 pr-2">
            {activeTab && (
              <div className="relative">
                <button
                  onClick={() => setShowHandoffMenu(!showHandoffMenu)}
                  className="flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 transition-colors mr-2"
                >
                  {handoffLoading ? (
                    <Loader2 size={13} className="animate-spin text-amber-500" />
                  ) : (
                    <Zap size={13} className="text-amber-500" />
                  )}
                  <span>Handoff</span>
                  <ChevronDown size={12} className={showHandoffMenu ? 'rotate-180 transition-transform' : 'transition-transform'} />
                </button>
                {showHandoffMenu && (
                  <div className="absolute right-0 top-full z-50 mt-1 min-w-[160px] rounded-xl border border-slate-200 bg-white p-1 shadow-lg backdrop-blur">
                    {AGENT_ENGINES.filter(e => e.id !== activeTab.engine).map(target => (
                      <button
                        key={target.id}
                        onClick={() => void handleHandoff(target.id)}
                        className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-100"
                      >
                        <span className={`h-2 w-2 rounded-full ${target.dot}`} />
                        <span>{target.nameKey ? t(target.nameKey) : target.name}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            <button onClick={toggleMaximize} className="rounded p-1.5 text-slate-400 hover:bg-slate-200 hover:text-slate-600" title="Maximize">
              {isMaximized ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
            </button>
            <button onClick={toggleDrawer} className="rounded p-1.5 text-slate-400 hover:bg-slate-200 hover:text-slate-600" title="Minimize Drawer">
              <ChevronDown size={16} />
            </button>
            <button onClick={() => isMaximized ? toggleMaximize() : toggleDrawer()} className="hidden">
              <X size={16} />
            </button>
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

        <div className="relative flex-1 min-h-0 bg-slate-900">
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
