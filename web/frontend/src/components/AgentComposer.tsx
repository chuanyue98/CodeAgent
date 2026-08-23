import { Loader2, Send, Square } from 'lucide-react';

type Props = {
  input: string;
  activeTurnId: string | null;
  connecting: boolean;
  sending: boolean;
  canCompose: boolean;
  composerPlaceholder: string;
  sessionCapabilitySnapshot: { supportsCancel?: boolean } | undefined;
  setComposerRef: (element: HTMLTextAreaElement | null) => void;
  onInputChange: (value: string) => void;
  onSend: () => void;
  onCancel: () => void;
};

export default function AgentComposer({
  input,
  activeTurnId,
  connecting,
  sending,
  canCompose,
  composerPlaceholder,
  sessionCapabilitySnapshot,
  setComposerRef,
  onInputChange,
  onSend,
  onCancel,
}: Props) {
  return (
    <div className="mt-3 flex items-end gap-2">
      <textarea
        ref={setComposerRef}
        value={input}
        rows={1}
        disabled={Boolean(activeTurnId) || !canCompose}
        onChange={event => {
          onInputChange(event.target.value);
          const el = event.target;
          el.style.height = 'auto';
          el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
        }}
        onKeyDown={event => {
          if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            void onSend();
          }
        }}
        placeholder={composerPlaceholder}
        className="max-h-40 min-h-10 flex-1 resize-none overflow-y-auto rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-primary disabled:opacity-50"
      />
      {activeTurnId ? (
        <button
          onClick={onCancel}
          disabled={!sessionCapabilitySnapshot?.supportsCancel}
          aria-label="停止智能体"
          // A greyed-out stop button during a long run is the worst moment to
          // leave someone guessing -- say whose limitation it is.
          title={
            sessionCapabilitySnapshot?.supportsCancel
              ? '停止智能体'
              : '该引擎无法在回合开始后将其中断。请等待其完成，或移除该会话。'
          }
          className="rounded-lg border border-red-200 bg-red-50 p-2.5 text-red-600 hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Square className="h-4 w-4 fill-current" />
        </button>
      ) : (
        <button
          onClick={() => void onSend()}
          disabled={!input.trim() || !canCompose || connecting || sending}
          aria-label="发送消息"
          className="rounded-lg bg-primary p-2.5 text-white hover:bg-primary/90 disabled:opacity-40"
        >
          {connecting || sending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
        </button>
      )}
    </div>
  );
}
