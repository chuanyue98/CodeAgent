import { useCallback, useEffect, useState } from 'react';
import { Check, Copy } from 'lucide-react';
import { useT } from '../i18n/context';
import MarkdownMessage from './MarkdownMessage';

type Props = {
  role: 'user' | 'assistant' | 'error' | string;
  text: string;
};

/**
 * One conversation bubble.
 *
 * Split out of AgentWorkspace so an assistant answer can carry a copy
 * action — the single most-used affordance in every chat product, and the
 * only way to get a generated snippet out of this UI without selecting it
 * by hand across a scrolling container.
 */
export default function AgentMessage({ role, text }: Props) {
  const t = useT();
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), 1800);
    return () => window.clearTimeout(timer);
  }, [copied]);

  const copy = useCallback(() => {
    void navigator.clipboard?.writeText(text).then(
      () => setCopied(true),
      () => setCopied(false),
    );
  }, [text]);

  const isAssistant = role === 'assistant';

  return (
    <div
      className={`group relative max-w-[85%] rounded-xl px-4 py-2.5 text-sm ${
        role === 'user'
          ? 'ml-auto bg-primary/10 text-slate-800'
          : role === 'error'
            ? 'border border-red-100 bg-red-50 text-red-700'
            : 'border border-slate-100 bg-slate-50 text-slate-700'
      }`}
    >
      {isAssistant
        ? <div className="prose prose-sm prose-slate max-w-none break-words"><MarkdownMessage text={text} /></div>
        : <span className="whitespace-pre-wrap">{text}</span>}

      {isAssistant && text.trim() && (
        <button
          type="button"
          onClick={copy}
          aria-label={copied ? t('agent.copied') : t('agent.copyMessage')}
          title={copied ? t('agent.copied') : t('agent.copyMessage')}
          // Always reachable by keyboard (focus:opacity-100); revealed on
          // hover for pointer users so it never competes with the text.
          className="absolute right-1.5 top-1.5 rounded-md border border-slate-200 bg-white p-1.5 text-slate-400 opacity-0 shadow-sm transition-opacity hover:text-slate-700 focus:opacity-100 group-hover:opacity-100"
        >
          {copied ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
        </button>
      )}
    </div>
  );
}
