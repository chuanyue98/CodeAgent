import { Terminal } from 'lucide-react';
import ResourceGallery, { type ResourceGalleryLabels } from './ResourceGallery';

const labels: ResourceGalleryLabels = {
  sidebar: 'gallery.sidebar',
  detailHeading: 'skills.detailHeading',
  backLabel: 'skills.back',
  searchLabel: 'skills.searchLabel',
  searchPlaceholder: 'skills.searchPlaceholder',
  searchId: 'skill-search',
  emptyCategory: 'skills.emptyCategory',
  itemSingular: 'noun.skill',
  itemPlural: 'noun.skills',
};

/**
 * Thin wrapper around the shared {@link ResourceGallery} for skills.
 * Only the kind-specific config (endpoint, icon, labels, resource key)
 * differs from PluginGallery; all rendering lives in ResourceGallery.
 */
function SkillGallery() {
  return (
    <ResourceGallery
      resourceType="skills"
      apiEndpoint="/api/skills"
      itemIcon={Terminal}
      labels={labels}
    />
  );
}

export default SkillGallery;
