import type { ReactElement } from 'react';
import { CheckSquare, Compass, FileText, Layers, ListOrdered, Target } from 'lucide-react';
import MarkdownMessage from '../MarkdownMessage';
import { useLanguageCode, useT } from '../../i18n/context';

export interface TaskBlueprintViewProps {
  content?: string;
  title: string;
}

type SectionKey = 'objective' | 'context' | 'instructions' | 'verification';

interface ParsedSections {
  objective: string;
  context: string;
  instructions: string;
  verification: string;
}

function classifySection(heading: string): SectionKey | null {
  const clean = heading.replace(/[*_`#]/g, '').trim().toLowerCase();

  // Objective / 目标
  if (
    clean === 'objective' ||
    clean === '目标' ||
    /^(objective|目标)\s*[(（/].*[)）]?$/i.test(clean) ||
    /^.*[(（/]\s*(objective|目标)\s*[)）]?$/i.test(clean)
  ) {
    if (
      !clean.includes('context') && !clean.includes('背景') &&
      !clean.includes('instruction') && !clean.includes('指令') &&
      !clean.includes('verification') && !clean.includes('验证') && !clean.includes('验收')
    ) {
      return 'objective';
    }
  }

  // Context / 背景
  if (
    clean === 'context' ||
    clean === '背景' ||
    /^(context|背景)\s*[(（/].*[)）]?$/i.test(clean) ||
    /^.*[(（/]\s*(context|背景)\s*[)）]?$/i.test(clean)
  ) {
    if (
      !clean.includes('objective') && !clean.includes('目标') &&
      !clean.includes('instruction') && !clean.includes('指令') &&
      !clean.includes('verification') && !clean.includes('验证') && !clean.includes('验收')
    ) {
      return 'context';
    }
  }

  // Instructions / 指令 / 执行指令
  if (
    clean === 'instruction' ||
    clean === 'instructions' ||
    clean === '指令' ||
    clean === '执行指令' ||
    /^(instructions?|指令|执行指令)\s*[(（/].*[)）]?$/i.test(clean) ||
    /^.*[(（/]\s*(instructions?|指令|执行指令)\s*[)）]?$/i.test(clean)
  ) {
    if (
      !clean.includes('objective') && !clean.includes('目标') &&
      !clean.includes('context') && !clean.includes('背景') &&
      !clean.includes('verification') && !clean.includes('验证') && !clean.includes('验收')
    ) {
      return 'instructions';
    }
  }

  // Verification / 验证 / 验收 / 验收标准
  if (
    clean === 'verification' ||
    clean === '验证' ||
    clean === '验收' ||
    clean === '验收标准' ||
    /^(verification|验证|验收|验收标准)\s*[(（/].*[)）]?$/i.test(clean) ||
    /^.*[(（/]\s*(verification|验证|验收|验收标准)\s*[)）]?$/i.test(clean)
  ) {
    if (
      !clean.includes('objective') && !clean.includes('目标') &&
      !clean.includes('context') && !clean.includes('背景') &&
      !clean.includes('instruction') && !clean.includes('指令')
    ) {
      return 'verification';
    }
  }

  return null;
}

function parseBlueprintSections(content: string): ParsedSections | null {
  if (!content || !content.trim()) return null;

  const lines = content.split('\n');
  let inCodeBlock = false;
  let currentSection: SectionKey | null = null;
  const sections: Record<SectionKey, string[]> = {
    objective: [],
    context: [],
    instructions: [],
    verification: [],
  };
  const seenSections = new Set<SectionKey>();

  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith('```') || trimmed.startsWith('~~~')) {
      inCodeBlock = !inCodeBlock;
      if (currentSection) {
        sections[currentSection].push(line);
      }
      continue;
    }

    if (!inCodeBlock) {
      const h2Match = line.match(/^##\s+(.+)$/);
      if (h2Match) {
        const headingText = h2Match[1].trim();
        const sectionType = classifySection(headingText);
        if (!sectionType) {
          // Unknown H2 heading -> fallback to freeform
          return null;
        }
        if (seenSections.has(sectionType)) {
          // Duplicate section -> fallback to freeform
          return null;
        }
        seenSections.add(sectionType);
        currentSection = sectionType;
        continue;
      }
    }

    if (currentSection) {
      sections[currentSection].push(line);
    } else {
      // Preamble: allow blank lines or a single top-level title `# ...`
      if (trimmed.startsWith('# ') && !trimmed.startsWith('## ')) {
        continue;
      }
      if (trimmed.length > 0) {
        // Any non-empty preamble text means not strictly four sections
        return null;
      }
    }
  }

  if (seenSections.size !== 4) {
    return null;
  }

  return {
    objective: sections.objective.join('\n').trim(),
    context: sections.context.join('\n').trim(),
    instructions: sections.instructions.join('\n').trim(),
    verification: sections.verification.join('\n').trim(),
  };
}

export default function TaskBlueprintView({ content, title }: TaskBlueprintViewProps): ReactElement {
  const t = useT();
  const lang = useLanguageCode();

  if (!content || !content.trim()) {
    return (
      <div className="glass-card p-8 border-dashed border-slate-200 text-center space-y-2">
        <Layers className="w-8 h-8 text-slate-300 mx-auto" />
        <p className="text-sm text-slate-400">
          {lang === 'zh' ? '暂无任务蓝图内容' : 'No blueprint content available'}
        </p>
      </div>
    );
  }

  const sections = parseBlueprintSections(content);

  // If content matches the four-section structure, render the structured cards
  if (sections) {
    return (
      <div className="space-y-4">
        {/* Objective Section */}
        <div className="glass-card p-5 border-primary/20 bg-primary/[0.03] space-y-3 relative overflow-hidden">
          <div className="flex items-center gap-2.5 text-primary font-semibold text-sm">
            <div className="p-1.5 rounded-lg bg-primary/10 text-primary">
              <Target className="w-4 h-4" />
            </div>
            <span>{t('taskDetail.objective')}</span>
          </div>
          <div className="text-sm text-slate-700 leading-relaxed pl-1">
            {sections.objective ? (
              <MarkdownMessage text={sections.objective} />
            ) : (
              <p className="text-xs text-slate-400 italic">—</p>
            )}
          </div>
        </div>

        {/* Context Section */}
        <div className="glass-card p-5 border-slate-200/70 bg-slate-50/50 space-y-3">
          <div className="flex items-center gap-2.5 text-slate-700 font-semibold text-sm">
            <div className="p-1.5 rounded-lg bg-slate-200/60 text-slate-600">
              <Compass className="w-4 h-4" />
            </div>
            <span>{t('taskDetail.context')}</span>
          </div>
          <div className="text-sm text-slate-700 leading-relaxed pl-1">
            {sections.context ? (
              <MarkdownMessage text={sections.context} />
            ) : (
              <p className="text-xs text-slate-400 italic">—</p>
            )}
          </div>
        </div>

        {/* Instructions Section */}
        <div className="glass-card p-5 border-slate-200 bg-white/80 space-y-3">
          <div className="flex items-center gap-2.5 text-slate-800 font-semibold text-sm">
            <div className="p-1.5 rounded-lg bg-slate-100 text-slate-700 border border-slate-200/60">
              <ListOrdered className="w-4 h-4" />
            </div>
            <span>{t('taskDetail.instructions')}</span>
          </div>
          <div className="text-sm text-slate-700 leading-relaxed pl-1">
            {sections.instructions ? (
              <MarkdownMessage text={sections.instructions} />
            ) : (
              <p className="text-xs text-slate-400 italic">—</p>
            )}
          </div>
        </div>

        {/* Verification Section */}
        <div className="glass-card p-5 border-emerald-200/70 bg-emerald-50/30 space-y-3">
          <div className="flex items-center gap-2.5 text-emerald-800 font-semibold text-sm">
            <div className="p-1.5 rounded-lg bg-emerald-100/70 text-emerald-700">
              <CheckSquare className="w-4 h-4" />
            </div>
            <span>{t('taskDetail.verification')}</span>
          </div>
          <div className="text-sm text-slate-700 leading-relaxed pl-1">
            {sections.verification ? (
              <MarkdownMessage text={sections.verification} />
            ) : (
              <p className="text-xs text-slate-400 italic">—</p>
            )}
          </div>
        </div>
      </div>
    );
  }

  // Freeform Markdown fallback
  return (
    <div className="glass-card p-6 border-slate-100 space-y-4">
      <div className="flex items-center gap-2 text-xs font-semibold text-slate-400 uppercase tracking-wider border-b border-slate-100 pb-3">
        <FileText className="w-4 h-4 text-slate-500" />
        <span>{title || t('taskDetail.tabBlueprint')}</span>
      </div>
      <div className="text-sm text-slate-700 leading-relaxed">
        <MarkdownMessage text={content} />
      </div>
    </div>
  );
}
