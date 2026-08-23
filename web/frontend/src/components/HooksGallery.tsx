import { Anchor, Terminal } from 'lucide-react';
import { useProject } from '../context/ProjectContext';
import ResourceGallery, { type ResourceData, type ResourceGalleryLabels, type ResourceItem } from './ResourceGallery';

interface HookRaw {
  id: string;
  name: string;
  event: string;
  description: string;
  path: string;
}

interface HookMeta {
  event: string;
  path: string;
}

const labels: ResourceGalleryLabels = {
  sidebar: '资源库',
  detailHeading: '钩子详情',
  backLabel: '返回钩子列表',
  searchLabel: '搜索钩子',
  searchPlaceholder: '搜索钩子…',
  searchId: 'hook-search',
  emptyCategory: '该分类下没有钩子。',
  emptySidebar: '未找到钩子。',
  itemSingular: 'hook',
};

/**
 * /api/hooks returns a flat list, but each id is "{category}/{hook_name}"
 * (see HookService.get_detailed_hooks), so the real category -- "base",
 * and whatever else gets added alongside it later -- can be recovered
 * without a backend change, giving Hooks the same sidebar grouping as
 * Skills/Plugins instead of a single flat bucket.
 */
function transformHooks(raw: unknown): ResourceData<HookMeta> {
  const list: HookRaw[] = Array.isArray(raw) ? raw : (raw as { hooks?: HookRaw[] })?.hooks ?? [];

  const grouped: ResourceData<HookMeta> = {};
  for (const hook of list) {
    const category = hook.id.includes('/') ? hook.id.split('/')[0] : 'base';
    (grouped[category] ??= []).push({
      id: hook.id,
      name: hook.name,
      description: hook.description,
      readme: hook.description || '_暂无描述。_',
      meta: { event: hook.event, path: hook.path },
    });
  }
  return grouped;
}

/**
 * Thin wrapper around the shared {@link ResourceGallery} for hooks. Hooks
 * have no long-form doc of their own (unlike skills' SKILL.md), so the
 * meta badges below carry the trigger event, script path, and active
 * status that used to be the whole point of this gallery's bespoke layout.
 */
function HooksGallery() {
  const { currentGroup, groups } = useProject();
  const isHookActive = (hookId: string) => groups[currentGroup]?.hooks?.includes(hookId) ?? false;

  const renderMeta = (item: ResourceItem<HookMeta>) => {
    const active = isHookActive(item.id);
    return (
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${
            active
              ? 'border-emerald-100 bg-emerald-50 text-emerald-700'
              : 'border-slate-100 bg-slate-50 text-slate-600'
          }`}
        >
          {item.meta?.event}
        </span>
        <span className="flex items-center gap-1.5 truncate rounded-lg bg-slate-50/50 p-1.5 font-mono text-[11px] text-slate-400">
          <Terminal className="h-3 w-3 flex-shrink-0" />
          <span className="truncate">{item.meta?.path}</span>
        </span>
      </div>
    );
  };

  return (
    <ResourceGallery<HookMeta>
      resourceType="hooks"
      apiEndpoint="/api/hooks"
      transformData={transformHooks}
      itemIcon={Anchor}
      labels={labels}
      renderMeta={renderMeta}
      getSearchableMeta={item => item.meta?.event ?? ''}
    />
  );
}

export default HooksGallery;
