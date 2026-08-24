import { useState } from 'react';
import { ChevronDown, ChevronRight, Loader2, Wrench, XCircle, Check } from 'lucide-react';
import { useT } from '../i18n/context';
import type { ToolCallMeta } from '../state/agentSessionReducer';

type Props = {
  tools: ToolCallMeta[];
};

/**
 * 连续一段工具调用的折叠展示。
 *
 * 参照 CodeBuddy / Claude Code 的交互：默认只显示一行"N 个工具调用"摘要，
 * 避免长任务把对话刷没；点击展开后逐个列出工具名与状态。
 */
export default function AgentToolGroup({ tools }: Props) {
  const t = useT();
  const [expanded, setExpanded] = useState(false);
  const running = tools.some(tool => tool.status === 'running');
  const failed = tools.filter(tool => tool.status === 'failed').length;

  return (
    <div className="max-w-[85%] rounded-xl border border-slate-100 bg-slate-50 text-xs">
      <button
        type="button"
        onClick={() => setExpanded(value => !value)}
        aria-expanded={expanded}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-slate-500 hover:text-slate-700"
      >
        {expanded
          ? <ChevronDown className="h-3.5 w-3.5 shrink-0" />
          : <ChevronRight className="h-3.5 w-3.5 shrink-0" />}
        {running
          ? <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-primary" />
          : <Wrench className="h-3.5 w-3.5 shrink-0" />}
        <span className="font-medium">
          {t('agent.toolsExecuted', { count: tools.length })}
        </span>
        {failed > 0 && (
          <span className="text-red-500">
            {t('agent.toolsFailed', { count: failed })}
          </span>
        )}
      </button>
      {expanded && (
        <ul className="space-y-1 border-t border-slate-100 px-3 py-2">
          {tools.map((tool, index) => (
            <li key={index} className="flex items-center gap-2 text-slate-600">
              {tool.status === 'running'
                ? <Loader2 className="h-3 w-3 shrink-0 animate-spin text-primary" />
                : tool.status === 'failed'
                  ? <XCircle className="h-3 w-3 shrink-0 text-red-500" />
                  : <Check className="h-3 w-3 shrink-0 text-emerald-600" />}
              <span className="break-all font-mono text-[11px]">{tool.label}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
