import { Zap } from 'lucide-react';
import ResourceGallery, { type ResourceGalleryLabels } from './ResourceGallery';

const labels: ResourceGalleryLabels = {
  // Same word as the other three galleries: one sidebar heading across all
  // Capabilities tabs reads as one feature, not four.
  sidebar: 'Library',
  detailHeading: 'Plugin Detail',
  backLabel: 'Back to plugin list',
  searchLabel: 'Search plugins',
  searchPlaceholder: 'Search plugins...',
  searchId: 'plugin-search',
  emptyCategory: 'No plugins found in this category.',
  emptySidebar: 'No plugins found',
  itemSingular: 'plugin',
};

/**
 * Thin wrapper around the shared {@link ResourceGallery} for plugins.
 * Only the kind-specific config (endpoint, icon, labels, resource key)
 * differs from SkillGallery; all rendering lives in ResourceGallery.
 */
function PluginGallery() {
  return (
    <ResourceGallery
      resourceType="plugins"
      apiEndpoint="/api/plugins"
      itemIcon={Zap}
      labels={labels}
    />
  );
}

export default PluginGallery;
