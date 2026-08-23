import { Terminal } from 'lucide-react';
import ResourceGallery, { type ResourceGalleryLabels } from './ResourceGallery';

const labels: ResourceGalleryLabels = {
  sidebar: '资源库',
  detailHeading: '技能详情',
  backLabel: '返回技能列表',
  searchLabel: '搜索技能',
  searchPlaceholder: '搜索技能…',
  searchId: 'skill-search',
  emptyCategory: '该分类下没有技能。',
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
