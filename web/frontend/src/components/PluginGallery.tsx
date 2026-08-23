import { Zap } from 'lucide-react';
import ResourceGallery, { type ResourceGalleryLabels } from './ResourceGallery';

const labels: ResourceGalleryLabels = {
  // Same word as the other three galleries: one sidebar heading across all
  // Capabilities tabs reads as one feature, not four.
  sidebar: '资源库',
  detailHeading: '插件详情',
  backLabel: '返回插件列表',
  searchLabel: '搜索插件',
  searchPlaceholder: '搜索插件…',
  searchId: 'plugin-search',
  emptyCategory: '该分类下没有插件。',
  emptySidebar: '未找到插件',
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
