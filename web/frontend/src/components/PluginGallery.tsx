import { Zap } from 'lucide-react';
import ResourceGallery, { type ResourceGalleryLabels } from './ResourceGallery';

const labels: ResourceGalleryLabels = {
  // Same word as the other three galleries: one sidebar heading across all
  // Capabilities tabs reads as one feature, not four.
  sidebar: 'gallery.sidebar',
  detailHeading: 'plugins.detailHeading',
  backLabel: 'plugins.back',
  searchLabel: 'plugins.searchLabel',
  searchPlaceholder: 'plugins.searchPlaceholder',
  searchId: 'plugin-search',
  emptyCategory: 'plugins.emptyCategory',
  emptySidebar: 'plugins.emptySidebar',
  itemSingular: 'noun.plugin',
  itemPlural: 'noun.plugins',
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
