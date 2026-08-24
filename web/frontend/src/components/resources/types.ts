/**
 * A single resource entry (skill, plugin, hook, prompt group).
 *
 * All four kinds share this shape, plus an optional `meta` bag for whatever
 * extra fields a given kind wants surfaced — a hook's event and script path,
 * a prompt group's file list.
 */
export interface ResourceItem<M = unknown> {
  name: string;
  id: string;
  description: string;
  readme: string;
  meta?: M;
}

/** Categorized resource data: category name -> items. */
export type ResourceData<M = unknown> = Record<string, ResourceItem<M>[]>;
