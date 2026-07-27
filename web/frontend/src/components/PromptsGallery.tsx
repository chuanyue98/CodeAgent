import { BookMarked, Files } from 'lucide-react';
import ResourceGallery, { type ResourceData, type ResourceGalleryLabels, type ResourceItem } from './ResourceGallery';

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

const labels: ResourceGalleryLabels = {
  sidebar: 'Library',
  detailHeading: 'Prompt Group',
  backLabel: 'Back to prompt group list',
  searchLabel: 'Search prompt groups',
  searchPlaceholder: 'Search prompt groups...',
  searchId: 'prompt-search',
  emptyCategory: 'No prompt groups found in this category.',
  emptySidebar: 'No prompt groups found.',
  itemSingular: 'prompt group',
};

/**
 * /api/prompts returns a flat list where each entry is itself a whole
 * category (a folder under prompt/, e.g. "base") combining all its files'
 * content into one readme -- there's no further per-category breakdown the
 * way skills/plugins have. Bucketing everything under one "All" key still
 * gives ResourceGallery a valid category -> items map, and leaves room for
 * a real breakdown later without another rewrite.
 */
function transformPrompts(raw: unknown): ResourceData<PromptMeta> {
  const list: PromptGroupRaw[] = Array.isArray(raw)
    ? raw
    : (raw as { prompts?: PromptGroupRaw[] })?.prompts ?? [];

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

function renderMeta(item: ResourceItem<PromptMeta>) {
  const files = item.meta?.files ?? [];
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="mr-1 text-[11px] font-bold uppercase tracking-widest text-slate-500">
        {files.length} file{files.length === 1 ? '' : 's'}
      </span>
      {files.slice(0, 4).map(file => (
        <span key={file.path} className="rounded-full border border-slate-100 bg-slate-50 px-2 py-1 text-[10px] font-semibold text-slate-600">
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

function renderDetailAside(item: ResourceItem<PromptMeta>) {
  const files = item.meta?.files ?? [];
  return (
    <>
      <div className="mb-4 flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-slate-500">
        <Files className="h-4 w-4 text-primary" />
        Files in Group
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

/**
 * Thin wrapper around the shared {@link ResourceGallery} for prompt groups.
 * Only the prompt-specific data reshape and file-list rendering differ from
 * SkillGallery/PluginGallery/HooksGallery; all interaction chrome (sidebar,
 * search, multi-select + batch activate, detail view) lives in ResourceGallery.
 */
function PromptsGallery() {
  return (
    <ResourceGallery<PromptMeta>
      resourceType="prompts"
      apiEndpoint="/api/prompts"
      transformData={transformPrompts}
      itemIcon={BookMarked}
      labels={labels}
      renderMeta={renderMeta}
      renderDetailAside={renderDetailAside}
    />
  );
}

export default PromptsGallery;
