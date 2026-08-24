import type { ReactNode } from 'react';
import { Anchor, BookMarked, Files, Terminal, Zap, type LucideIcon } from 'lucide-react';
import type { GroupDefinition } from '../../context/ProjectContext';
import type { Translate } from '../../i18n/context';
import type { TranslationKey } from '../../i18n/locales/en';
import type { ResourceData, ResourceItem } from './types';

/**
 * The four kinds scoped by resource group. MCP is deliberately absent: it is
 * configured per *engine* (`/api/mcp/{engine}`), not per group, so folding it
 * into this list would produce a kind filter whose group selector silently
 * stops meaning anything the moment you pick it.
 */
export type ResourceKindId = keyof GroupDefinition;

export interface ResourceKindConfig<M = unknown> {
  /** Doubles as the GroupDefinition key the toggle writes to. */
  id: ResourceKindId;
  labelKey: TranslationKey;
  apiEndpoint: string;
  itemIcon: LucideIcon;
  detailHeadingKey: TranslationKey;
  itemSingularKey: TranslationKey;
  itemPluralKey: TranslationKey;
  /** Shown in the sidebar when this kind has nothing at all. */
  emptyKindKey?: TranslationKey;
  /** Reshapes endpoints that return a flat list into category -> items. */
  transformData?: (raw: unknown, t: Translate) => ResourceData<M>;
  /** Kind-specific badges under the card description and detail header. */
  renderMeta?: (item: ResourceItem<M>, t: Translate, active: boolean) => ReactNode;
  /** Optional second column beside the detail view's markdown body. */
  renderDetailAside?: (item: ResourceItem<M>, t: Translate) => ReactNode;
  /** Extra text the search should match, beyond name and description. */
  getSearchableMeta?: (item: ResourceItem<M>) => string;
}

/**
 * Erases the per-kind meta type so the kinds can live in one array.
 *
 * Each entry is still checked against its own `M` at the call site; only the
 * table is homogeneous. The alternative — a union type threaded through every
 * render path — buys nothing, because the closures that read `meta` are
 * defined right here next to the type that produced it.
 */
function defineKind<M>(config: ResourceKindConfig<M>): ResourceKindConfig {
  return config as ResourceKindConfig;
}

// ── Prompts ──────────────────────────────────────────────────────────────────
interface PromptFile {
  name: string;
  path: string;
}

interface PromptGroupRaw {
  id: string;
  name: string;
  description: string;
  readme: string;
  files: PromptFile[];
}

interface PromptMeta {
  files: PromptFile[];
}

/**
 * /api/prompts returns a flat list where each entry is itself a whole
 * category (a folder under prompt/, e.g. "base") combining all its files'
 * content into one readme — there is no further per-category breakdown the
 * way skills and plugins have. Bucketing under one "All" key still yields a
 * valid category -> items map.
 */
function transformPrompts(raw: unknown): ResourceData<PromptMeta> {
  const list: PromptGroupRaw[] = Array.isArray(raw)
    ? raw
    : ((raw as { prompts?: PromptGroupRaw[] })?.prompts ?? []);

  return {
    All: list.map(group => ({
      id: group.id,
      name: group.name,
      description: group.description,
      readme: group.readme,
      meta: { files: group.files },
    })),
  };
}

function renderPromptMeta(item: ResourceItem<PromptMeta>, t: Translate) {
  const files = item.meta?.files ?? [];
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="mr-1 text-[11px] font-bold uppercase tracking-widest text-slate-500">
        {files.length === 1
          ? t('prompts.fileCountOne')
          : t('prompts.fileCount', { count: files.length })}
      </span>
      {files.slice(0, 4).map(file => (
        <span
          key={file.path}
          className="rounded-full border border-slate-100 bg-slate-50 px-2 py-1 text-[10px] font-semibold text-slate-600"
        >
          {file.name}
        </span>
      ))}
      {files.length > 4 && (
        <span className="rounded-full border border-slate-100 bg-slate-50 px-2 py-1 text-[10px] font-semibold text-slate-600">
          +{files.length - 4}
        </span>
      )}
    </div>
  );
}

function renderPromptAside(item: ResourceItem<PromptMeta>, t: Translate) {
  const files = item.meta?.files ?? [];
  return (
    <>
      <div className="mb-4 flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-slate-500">
        <Files className="h-4 w-4 text-primary" />
        {t('prompts.filesInGroup')}
      </div>
      <div className="space-y-2">
        {files.map(file => (
          <div key={file.path} className="rounded-xl border border-slate-200 bg-white px-4 py-3">
            <div className="text-sm font-semibold text-slate-800">{file.name}</div>
            <div className="mt-1 break-all font-mono text-[11px] text-slate-500">{file.path}</div>
          </div>
        ))}
      </div>
    </>
  );
}

// ── Hooks ────────────────────────────────────────────────────────────────────
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

/**
 * /api/hooks returns a flat list, but each id is "{category}/{hook_name}"
 * (see HookService.get_detailed_hooks), so the real category can be recovered
 * without a backend change.
 */
function transformHooks(raw: unknown, t: Translate): ResourceData<HookMeta> {
  const list: HookRaw[] = Array.isArray(raw)
    ? raw
    : ((raw as { hooks?: HookRaw[] })?.hooks ?? []);

  const grouped: ResourceData<HookMeta> = {};
  for (const hook of list) {
    const category = hook.id.includes('/') ? hook.id.split('/')[0] : 'base';
    (grouped[category] ??= []).push({
      id: hook.id,
      name: hook.name,
      description: hook.description,
      readme: hook.description || t('gallery.noDescription'),
      meta: { event: hook.event, path: hook.path },
    });
  }
  return grouped;
}

/** Active state arrives as an argument so this table stays a plain constant. */
function renderHookMeta(item: ResourceItem<HookMeta>, _t: Translate, active: boolean) {
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
}

// ── The table ────────────────────────────────────────────────────────────────
export const RESOURCE_KINDS: readonly ResourceKindConfig[] = [
  defineKind({
    id: 'skills',
    labelKey: 'resources.kind.skills',
    apiEndpoint: '/api/skills',
    itemIcon: Terminal,
    detailHeadingKey: 'skills.detailHeading',
    itemSingularKey: 'noun.skill',
    itemPluralKey: 'noun.skills',
  }),
  defineKind<PromptMeta>({
    id: 'prompts',
    labelKey: 'resources.kind.prompts',
    apiEndpoint: '/api/prompts',
    itemIcon: BookMarked,
    detailHeadingKey: 'prompts.detailHeading',
    itemSingularKey: 'noun.promptGroup',
    itemPluralKey: 'noun.promptGroups',
    emptyKindKey: 'prompts.emptySidebar',
    transformData: transformPrompts,
    renderMeta: renderPromptMeta,
    renderDetailAside: renderPromptAside,
  }),
  defineKind<HookMeta>({
    id: 'hooks',
    labelKey: 'resources.kind.hooks',
    apiEndpoint: '/api/hooks',
    itemIcon: Anchor,
    detailHeadingKey: 'hooks.detailHeading',
    itemSingularKey: 'noun.hook',
    itemPluralKey: 'noun.hooks',
    emptyKindKey: 'hooks.emptySidebar',
    transformData: transformHooks,
    renderMeta: renderHookMeta,
    getSearchableMeta: item => item.meta?.event ?? '',
  }),
  defineKind({
    id: 'plugins',
    labelKey: 'resources.kind.plugins',
    apiEndpoint: '/api/plugins',
    itemIcon: Zap,
    detailHeadingKey: 'plugins.detailHeading',
    itemSingularKey: 'noun.plugin',
    itemPluralKey: 'noun.plugins',
    emptyKindKey: 'plugins.emptySidebar',
  }),
];

export function kindById(id: string): ResourceKindConfig | undefined {
  return RESOURCE_KINDS.find(kind => kind.id === id);
}
