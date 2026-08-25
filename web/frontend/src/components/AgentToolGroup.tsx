import { useState } from 'react';
import { Check, ChevronDown, ChevronRight, FileDiff, Loader2, Wrench, XCircle } from 'lucide-react';
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
  // file.diff and command.output were arriving at the browser and being
  // dropped; surfacing the file count here is what makes a collapsed group
  // worth expanding.
  const changedFiles = new Set(tools.flatMap(tool => tool.files ?? []));

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
        {changedFiles.size > 0 && (
          <span className="flex items-center gap-1 text-slate-500">
            <FileDiff className="h-3 w-3 shrink-0" />
            {t('agent.filesChanged', { count: changedFiles.size })}
          </span>
        )}
      </button>
      {expanded && (
        <ul className="space-y-1 border-t border-slate-100 px-3 py-2">
          {tools.map((tool, index) => (
            <li key={index} className="text-slate-600">
              <div className="flex items-center gap-2">
                {tool.status === 'running'
                  ? <Loader2 className="h-3 w-3 shrink-0 animate-spin text-primary" />
                  : tool.status === 'failed'
                    ? <XCircle className="h-3 w-3 shrink-0 text-red-500" />
                    : <Check className="h-3 w-3 shrink-0 text-emerald-600" />}
                <span className="break-all font-mono text-[11px]">{tool.label}</span>
              </div>
              {tool.files && tool.files.length > 0 && (
                <ul className="mt-1 ml-5 space-y-0.5">
                  {tool.files.map(file => (
                    <li key={file} className="flex items-center gap-1 text-[10px] text-slate-500">
                      <FileDiff className="h-2.5 w-2.5 shrink-0" />
                      <span className="break-all font-mono">{file}</span>
                    </li>
                  ))}
                </ul>
              )}
              {tool.output && (
                // Streamed while the command runs, so the tail is the live
                // end of it rather than a post-hoc dump.
                <pre className="custom-scrollbar mt-1 ml-5 max-h-40 overflow-auto rounded-md bg-slate-900 px-2 py-1.5 text-[10px] leading-relaxed text-slate-100">
                  {tool.output}
                </pre>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
