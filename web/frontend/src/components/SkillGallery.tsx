import { Terminal } from 'lucide-react';
import ResourceGallery, { type ResourceGalleryLabels } from './ResourceGallery';

const labels: ResourceGalleryLabels = {
  sidebar: 'Library',
  detailHeading: 'Skill Detail',
  backLabel: 'Back to skill list',
  searchLabel: 'Search skills',
  searchPlaceholder: 'Search skills...',
  searchId: 'skill-search',
  emptyCategory: 'No skills found in this category.',
  itemSingular: 'skill',
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
