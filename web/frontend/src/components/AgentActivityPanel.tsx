import { X } from 'lucide-react';
import type { AgentEvent } from '../types/agent';

type Props = {
  showActivity: boolean;
  activity: AgentEvent[];
  onClose: () => void;
};

export default function AgentActivityPanel({
  showActivity,
  activity,
  onClose,
}: Props) {
  if (!showActivity) return null;

  return (
    <aside className="glass-card flex w-80 shrink-0 flex-col p-4">
      <div className="mb-3 flex items-center justify-between border-b border-slate-100 pb-3">
        <div>
          <p className="text-sm font-semibold text-slate-800">回合事件</p>
          <p className="text-[10px] text-slate-400">
            工具、diff、用量和协议事件
          </p>
        </div>
        <button
          aria-label="关闭回合事件"
          onClick={onClose}
          className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-50"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="custom-scrollbar min-h-0 flex-1 space-y-2 overflow-y-auto">
        {activity.length === 0 && (
          <p className="text-xs italic text-slate-400">暂无事件</p>
        )}
        {activity.map(event => (
          <details
            key={event.sequence}
            className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2 text-xs"
          >
            <summary className="cursor-pointer font-medium text-slate-700">
              #{event.sequence} {event.type}
            </summary>
            <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap text-[10px] text-slate-500">
              {JSON.stringify(event.data, null, 2)}
            </pre>
          </details>
        ))}
      </div>
    </aside>
  );
}
