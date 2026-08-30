import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import {
  AlertCircle,
  ArrowDownToLine,
  ArrowUpToLine,
  Check,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Loader2,
  Play,
  TerminalSquare,
  Trash2,
  X,
} from 'lucide-react';
import { useNavigate } from 'react-router';
import {
  continueSession,
  convertAndLaunchSession,
  deleteHistorySession,
  fetchSessionDetail,
  type ResumeTarget,
  type SessionDetail,
} from '../api/audit';
import { type SessionUsage, fmtCost, fmtTokens } from '../api/analytics';
import { ALL_ENGINES, READ_ONLY_ENGINES, engineLabel } from '../utils/engines';
import ConfirmDialog from './shared/ConfirmDialog';
import Badge from './shared/Badge';
import Button from './shared/Button';
import SectionLabel from './shared/SectionLabel';
import { useT } from '../i18n/context';
import MarkdownMessage from './MarkdownMessage';
import SessionProgress from './SessionProgress';

/**
 * Transcript messages rendered at once. A long session is ~1,700 messages
 * of markdown, which committed in one synchronous render and left you at
 * message 1 of a conversation you opened to read the end of.
 */
const TRANSCRIPT_PAGE = 50;

/**
 * OpenCode names a subagent run "<what it did> (@explore subagent)". The
 * agent is a badge of its own beside the title here, so the suffix is the
 * same word twice.
 */
function withoutAgentSuffix(title: string, agent?: string): string {
  if (!agent) return title;
  const suffix = ` (@${agent} subagent)`;
  return title.endsWith(suffix) ? title.slice(0, -suffix.length) : title;
}

type ConvertState =
  | { status: 'idle' }
  | { status: 'loading'; targetEngine: string }
  | { status: 'success'; targetEngine: string; message: string }
  | { status: 'error'; targetEngine: string; message: string };

export interface SessionDetailPanelProps {
  engine: string;
  sessionId: string;
  projectPath: string;
  /** Usage totals, when the caller already has them (History does). */
  usage?: SessionUsage;
  onClose: () => void;
  /** Fired after a successful delete so the caller can drop its row. */
  onDeleted?: () => void;
  /**
   * Set when this panel is showing a subagent run reached from its parent.
   * A subagent run has no context of its own to resume or convert, so those
   * actions are replaced by a way back up.
   */
  parent?: { title: string; onBack: () => void };
}

/**
 * Everything about one session in one place: what it cost, what was actually
 * said in it, and the actions that operate on it.
 *
 * These used to be split across two tabs — History could show usage and
 * delete, Events could show the transcript and convert — so answering "what
 * did I discuss in that session?" meant crossing between them.
 */
export default function SessionDetailPanel({
  engine,
  sessionId,
  projectPath,
  usage,
  onClose,
  onDeleted,
  parent,
}: SessionDetailPanelProps) {
  const t = useT();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  const [resumeError, setResumeError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [convertState, setConvertState] = useState<ConvertState>({ status: 'idle' });
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [openSubtask, setOpenSubtask] = useState<SessionUsage | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [visibleCount, setVisibleCount] = useState(TRANSCRIPT_PAGE);
  /** Distance from the bottom to restore after prepending older messages. */
  const anchorFromBottomRef = useRef<number | null>(null);

  const messages = detail?.messages ?? [];
  const hiddenCount = Math.max(0, messages.length - visibleCount);
  const visibleMessages = hiddenCount > 0 ? messages.slice(hiddenCount) : messages;

  const scrollTo = useCallback((edge: 'top' | 'bottom') => {
    const element = scrollRef.current;
    if (!element) return;
    element.scrollTo({
      top: edge === 'top' ? 0 : element.scrollHeight,
      behavior: 'smooth',
    });
  }, []);

  // Which jump buttons are worth showing: the one pointing at the edge you
  // are already sitting on is noise.
  const [scrollEdges, setScrollEdges] = useState({ atTop: true, atBottom: true });

  const syncScrollEdges = useCallback(() => {
    const element = scrollRef.current;
    if (!element) return;
    const slack = 24;
    setScrollEdges({
      atTop: element.scrollTop <= slack,
      atBottom:
        element.scrollHeight - element.scrollTop - element.clientHeight <= slack,
    });
  }, []);

  // A transcript is read from the end: the last thing the engine said is why
  // you opened it. Jump there once the messages land, without animating
  // through everything above.
  useEffect(() => {
    if (!detail) return;
    const element = scrollRef.current;
    if (element) element.scrollTop = element.scrollHeight;
    syncScrollEdges();
  }, [detail, syncScrollEdges]);

  // Prepending older messages moves everything down by their height. Restore
  // the distance from the bottom so the row you were reading stays put.
  useLayoutEffect(() => {
    const anchor = anchorFromBottomRef.current;
    if (anchor === null) return;
    anchorFromBottomRef.current = null;
    const element = scrollRef.current;
    if (element) element.scrollTop = element.scrollHeight - anchor;
    syncScrollEdges();
  }, [visibleCount, syncScrollEdges]);

  const loadEarlier = useCallback(() => {
    const element = scrollRef.current;
    anchorFromBottomRef.current = element
      ? element.scrollHeight - element.scrollTop
      : null;
    setVisibleCount(previous => previous + TRANSCRIPT_PAGE);
  }, []);

  useEffect(() => {
    let mounted = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    setLoadError(null);
    setDetail(null);
    setConvertState({ status: 'idle' });
    setDeleteError(null);
    setVisibleCount(TRANSCRIPT_PAGE);

    fetchSessionDetail(engine, sessionId, projectPath)
      .then(data => {
        if (!mounted) return;
        setDetail(data);
        setLoading(false);
      })
      .catch(() => {
        if (!mounted) return;
        setLoading(false);
        setLoadError(t('sessionDetail.loadFailed'));
      });

    return () => {
      mounted = false;
    };
  }, [engine, sessionId, projectPath, t]);

  /** Hands a session to the terminal on the Agent page. */
  const openInBrowserTerminal = (target: ResumeTarget) => {
    const query = new URLSearchParams({
      engine: target.engine,
      cwd: target.project,
      session: target.sessionId,
    });
    navigate(`/agent/terminal?${query}`);
  };

  const handleContinue = async () => {
    setResumeError(null);
    try {
      // The endpoint validates the workspace and the session, then says what
      // to attach a terminal to -- it does not start anything itself.
      const target = await continueSession(engine, sessionId, projectPath);
      openInBrowserTerminal(target);
    } catch (err) {
      setResumeError(
        err instanceof Error ? err.message : t('sessionDetail.resumeFailed'),
      );
    }
  };

  const handleConvert = async (targetEngine: string) => {
    setConvertState({ status: 'loading', targetEngine });
    try {
      const result = await convertAndLaunchSession({
        sourceEngine: engine,
        sessionId,
        targetEngine,
        projectPath,
      });
      setConvertState({
        status: 'success',
        targetEngine,
        message: t('sessionDetail.opened', { engine: engineLabel(targetEngine), id: result.newSessionId }),
      });
      // The converted session is addressed like any other, so it opens in the
      // same terminal rather than in a window on the server's desktop.
      openInBrowserTerminal(result);
    } catch (err) {
      setConvertState({
        status: 'error',
        targetEngine,
        message: err instanceof Error ? err.message : t('sessionDetail.conversionFailed'),
      });
    }
  };

  const handleDelete = async () => {
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteHistorySession(engine, sessionId, projectPath);
      setDeleting(false);
      setConfirmingDelete(false);
      onDeleted?.();
      onClose();
    } catch (err) {
      setDeleting(false);
      setConfirmingDelete(false);
      setDeleteError(err instanceof Error ? err.message : t('sessionDetail.deleteFailed'));
    }
  };

  const projectName = projectPath.split(/[\\/]/).filter(Boolean).pop() || projectPath || '—';
  const totalTokens = usage ? usage.inputTokens + usage.outputTokens : 0;
  const subtasks = usage?.subtasks ?? [];
  const own = usage?.own;
  const ownTokens = own ? own.inputTokens + own.outputTokens : 0;

  // Every hook above has run by now, so swapping the whole panel out for a
  // subtask is safe here and nowhere earlier.
  if (openSubtask) {
    return (
      <SessionDetailPanel
        key={`${openSubtask.target}::${openSubtask.sessionId}`}
        engine={openSubtask.target}
        sessionId={openSubtask.sessionId}
        projectPath={openSubtask.projectPath}
        usage={openSubtask}
        onClose={onClose}
        parent={{
          title: detail?.title || usage?.title || projectName,
          onBack: () => setOpenSubtask(null),
        }}
      />
    );
  }

  return (
    <div data-testid="session-detail" className="flex h-full min-h-0 flex-col">
      <div className="flex items-start justify-between gap-2 border-b border-slate-100 pb-3">
        <div className="min-w-0">
          {parent && (
            <button
              onClick={parent.onBack}
              className="mb-1 flex max-w-full items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
            >
              <ChevronLeft className="h-3.5 w-3.5 shrink-0" />
              <span className="truncate">{parent.title}</span>
            </button>
          )}
          <h3 className="truncate text-sm font-semibold text-slate-800">
            {detail?.title || projectName}
          </h3>
          <p className="mt-0.5 truncate text-xs text-slate-400" title={projectPath}>
            {projectPath}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Badge variant="engine" engine={engine}>{engine}</Badge>
          <button
            aria-label={t('sessionDetail.close')}
            onClick={onClose}
            className="text-slate-400 transition-colors hover:text-slate-600"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* overflow-x-hidden is explicit: setting only overflow-y makes the
          other axis compute to `auto`, so the whole panel picked up a
          horizontal scrollbar whenever one line of a transcript was long.
          Code blocks keep their own — wrapping code would mangle it. */}
      <div className="relative flex min-h-0 flex-1 flex-col">
        <div
          ref={scrollRef}
          data-testid="session-scroll"
          onScroll={syncScrollEdges}
          className="custom-scrollbar min-h-0 flex-1 space-y-4 overflow-y-auto overflow-x-hidden pt-3"
        >
          <SessionProgress detail={detail} usage={usage} />

          {usage && (
            <section data-testid="session-usage">
              <SectionLabel className="mb-2">{t('sessionDetail.usage')}</SectionLabel>
              <div className="mb-2 grid grid-cols-2 gap-2">
                <div className="rounded-lg border border-slate-100 bg-slate-50/70 p-2 text-center">
                  <p className="text-sm font-bold text-slate-800">{fmtTokens(totalTokens)}</p>
                  <p className="text-[10px] uppercase tracking-wide text-slate-500">Token</p>
                </div>
                <div className="rounded-lg border border-slate-100 bg-slate-50/70 p-2 text-center">
                  <p className="text-sm font-bold text-slate-800">{fmtCost(usage.cost)}</p>
                  <p className="text-[10px] uppercase tracking-wide text-slate-500">{t('sessionDetail.estCost')}</p>
                </div>
              </div>
              {subtasks.length > 0 && own && (
                <div className="mb-2 flex flex-wrap gap-4 text-xs text-slate-500">
                  <span>
                    {t('sessionDetail.ownShare', {
                      tokens: fmtTokens(ownTokens),
                      cost: fmtCost(own.cost),
                    })}
                  </span>
                  <span>
                    {t('sessionDetail.subtaskShare', {
                      tokens: fmtTokens(totalTokens - ownTokens),
                      cost: fmtCost(usage.cost - own.cost),
                    })}
                  </span>
                </div>
              )}
              {usage.modelBreakdowns?.length > 0 && (
                <div className="space-y-1">
                  {usage.modelBreakdowns.map((mb, i) => (
                    <div key={`${mb.modelName}-${i}`} className="flex flex-wrap items-center justify-between gap-2 text-xs">
                      <span className="min-w-0 break-all font-mono text-slate-600">{mb.modelName}</span>
                      <div className="flex flex-wrap gap-3 text-slate-500">
                        <span>{t('sessionDetail.in', { tokens: fmtTokens(mb.inputTokens) })}</span>
                        <span>{t('sessionDetail.out', { tokens: fmtTokens(mb.outputTokens) })}</span>
                        <span className="font-semibold text-slate-700">{fmtCost(mb.cost)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              <div className="mt-2 flex flex-wrap gap-4 border-t border-slate-50 pt-2 text-xs text-slate-500">
                <span>{t('sessionDetail.cacheWrite', { tokens: fmtTokens(usage.cacheCreationTokens) })}</span>
                <span>{t('sessionDetail.cacheRead', { tokens: fmtTokens(usage.cacheReadTokens) })}</span>
              </div>
            </section>
          )}

          {subtasks.length > 0 && (
            <section data-testid="session-subtasks">
              <SectionLabel className="mb-2">
                {t('sessionDetail.subtasks', { count: subtasks.length })}
              </SectionLabel>
              <div className="space-y-1">
                {subtasks.map(child => (
                  <button
                    key={`${child.target}::${child.sessionId}`}
                    onClick={() => setOpenSubtask(child)}
                    className="flex w-full items-center gap-2 rounded-lg border border-slate-100 px-2 py-1.5 text-left text-xs transition-colors hover:bg-slate-50"
                  >
                    {child.agent && <Badge size="sm">{child.agent}</Badge>}
                    <span className="min-w-0 flex-1 truncate text-slate-700">
                      {withoutAgentSuffix(child.title || '', child.agent) || child.sessionId}
                    </span>
                    <span className="shrink-0 text-slate-500">
                      {fmtTokens(child.inputTokens + child.outputTokens)}
                    </span>
                    <span className="shrink-0 text-slate-500">{fmtCost(child.cost)}</span>
                    <ChevronRight className="h-3.5 w-3.5 shrink-0 text-slate-300" />
                  </button>
                ))}
              </div>
            </section>
          )}

          <section>
            <SectionLabel className="mb-2">{t('sessionDetail.conversation')}</SectionLabel>
            {loading && (
              <p className="flex items-center gap-2 text-xs text-slate-400">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> {t('sessionDetail.loadingConversation')}
              </p>
            )}
            {!loading && loadError && <p className="text-xs text-slate-400">{loadError}</p>}
            {!loading && !loadError && detail && messages.length === 0 && (
              <p className="text-xs text-slate-400">{t('sessionDetail.noMessages')}</p>
            )}
            {!loading && !loadError && detail && messages.length > 0 && (
              <div className="space-y-3">
                {hiddenCount > 0 && (
                  <button
                    onClick={loadEarlier}
                    className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-dashed border-slate-200 py-2 text-xs font-medium text-slate-500 transition-colors hover:bg-slate-50 hover:text-slate-700"
                  >
                    <ChevronUp className="h-3.5 w-3.5" />
                    {t('sessionDetail.loadEarlier', {
                      shown: String(visibleMessages.length),
                      total: String(messages.length),
                    })}
                  </button>
                )}
                {visibleMessages.map((msg, i) => (
                  <div
                    key={`${msg.timestamp}-${msg.role}-${hiddenCount + i}`}
                    className="rounded-lg border border-slate-100 p-3"
                  >
                    <div className="mb-1 flex items-center justify-between">
                      <span className="text-xs font-semibold uppercase text-slate-600">{msg.role}</span>
                      <span className="text-[10px] text-slate-400">
                        {msg.timestamp ? new Date(msg.timestamp).toLocaleString() : ''}
                      </span>
                    </div>
                    {/* Same rendering the Agent page gives these messages: they
                        are the transcript of a session an engine wrote in
                        markdown, so showing them raw meant a wall of ** and
                        backticks in the one place you go to read them back. */}
                    <div className="prose prose-sm prose-slate max-w-none break-words">
                      <MarkdownMessage text={msg.content} />
                    </div>
                    {msg.toolCalls?.length > 0 && (
                      <div className="mt-2 space-y-1">
                        {msg.toolCalls.map((tc, j) => (
                          <div key={`${tc.name}-${j}`} className="rounded bg-slate-50 p-1.5 text-[11px]">
                            <span className="font-mono font-semibold">{tc.name}</span>
                            {tc.argsPreview && <span className="text-slate-500"> — {tc.argsPreview}</span>}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>

        {/* Pinned to the viewport, not to the transcript header: the panel
            opens at the newest message, so a control that scrolls away with
            the content is unreachable exactly when it is wanted. */}
        <div className="pointer-events-none absolute bottom-3 right-3 flex flex-col gap-1">
          {!scrollEdges.atTop && (
            <button
              aria-label={t('sessionDetail.toTop')}
              title={t('sessionDetail.toTop')}
              onClick={() => scrollTo('top')}
              className="pointer-events-auto rounded-full border border-slate-200 bg-white/90 p-1.5 text-slate-500 shadow-sm backdrop-blur transition-colors hover:bg-slate-50 hover:text-slate-700"
            >
              <ArrowUpToLine className="h-3.5 w-3.5" />
            </button>
          )}
          {!scrollEdges.atBottom && (
            <button
              aria-label={t('sessionDetail.toBottom')}
              title={t('sessionDetail.toBottom')}
              onClick={() => scrollTo('bottom')}
              className="pointer-events-auto rounded-full border border-slate-200 bg-white/90 p-1.5 text-slate-500 shadow-sm backdrop-blur transition-colors hover:bg-slate-50 hover:text-slate-700"
            >
              <ArrowDownToLine className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      <div className="space-y-2 border-t border-slate-100 pt-3">
        {parent ? (
          <p className="text-xs text-slate-400">{t('sessionDetail.subtaskOfParent')}</p>
        ) : (
        <>
        <Button className="w-full" icon={Play} onClick={() => void handleContinue()}>
          {t('sessionDetail.continue')}
        </Button>
        {resumeError && (
          <p className="flex items-center gap-1.5 text-xs text-red-600">
            <AlertCircle className="h-3.5 w-3.5 shrink-0" /> {resumeError}
          </p>
        )}

        <SectionLabel className="pt-1">{t('sessionDetail.openInAnother')}</SectionLabel>
        <div className="flex flex-wrap gap-2">
          {ALL_ENGINES.filter(target => target !== engine && !READ_ONLY_ENGINES.has(target)).map(target => (
            <Button
              key={target}
              variant="outline"
              size="sm"
              icon={TerminalSquare}
              disabled={convertState.status === 'loading'}
              onClick={() => void handleConvert(target)}
            >
              {engineLabel(target)}
              {convertState.status === 'loading' && convertState.targetEngine === target && '…'}
            </Button>
          ))}
        </div>
        {convertState.status === 'success' && (
          <p className="flex items-center gap-1.5 text-xs text-emerald-600">
            <Check className="h-3.5 w-3.5 shrink-0" /> {convertState.message}
          </p>
        )}
        {convertState.status === 'error' && (
          <p className="flex items-center gap-1.5 text-xs text-red-600">
            <AlertCircle className="h-3.5 w-3.5 shrink-0" /> {convertState.message}
          </p>
        )}

        {deleteError && (
          <p className="flex items-center gap-1.5 text-xs text-red-600">
            <AlertCircle className="h-3.5 w-3.5 shrink-0" /> {deleteError}
          </p>
        )}
        <Button variant="destructive" size="sm" icon={Trash2} onClick={() => setConfirmingDelete(true)}>
          {t('sessionDetail.delete')}
        </Button>
        </>
        )}
        <p className="truncate font-mono text-[10px] text-slate-300" title={sessionId}>
          {sessionId}
        </p>
      </div>

      {confirmingDelete && (
        <ConfirmDialog
          title={t('sessionDetail.confirmDeleteTitle')}
          description={t('sessionDetail.confirmDeleteDescription')}
          confirmLabel={deleting ? t('sessionDetail.deleting') : t('common.delete')}
          onConfirm={() => { if (!deleting) void handleDelete(); }}
          onCancel={() => { if (!deleting) setConfirmingDelete(false); }}
        />
      )}
    </div>
  );
}
