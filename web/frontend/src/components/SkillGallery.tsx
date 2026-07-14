import React, { useState, useEffect } from 'react';
import { Search, BookOpen, Layers, Terminal, Globe, Cpu, ChevronRight } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { useProject } from '../context/ProjectContext';
import Toggle from './shared/Toggle';
import ErrorState from './shared/ErrorState';
import LoadingState from './shared/LoadingState';
import useResourceData from '../hooks/useResourceData';
import useResourceToggle from '../hooks/useResourceToggle';

interface Skill {
  name: string;
  id: string;
  description: string;
  readme: string;
}

interface SkillsData {
  [category: string]: Skill[];
}

const SkillGallery: React.FC = () => {
  const { currentGroup, groups } = useProject();
  const { data: skillsData, loading, error, refetch } = useResourceData<SkillsData>('/api/skills');
  const { toggleResource, toggleError } = useResourceToggle();
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null);
  const [searchTerm, setSearchTerm] = useState('');

  useEffect(() => {
    if (skillsData) {
      const categories = Object.keys(skillsData);
      if (categories.length > 0 && !selectedCategory) {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setSelectedCategory(categories[0]);
      }
    }
  }, [skillsData, selectedCategory]);

  const isSkillActive = (skillId: string) => {
    return groups[currentGroup]?.skills?.includes(skillId) ?? false;
  };

  const getCategoryIcon = (category: string) => {
    switch (category.toLowerCase()) {
      case 'base': return <Cpu className="w-4 h-4" />;
      case 'web': return <Globe className="w-4 h-4" />;
      case 'devops': return <Terminal className="w-4 h-4" />;
      default: return <Layers className="w-4 h-4" />;
    }
  };

  const filteredSkills = selectedCategory && skillsData
    ? skillsData[selectedCategory].filter(skill =>
        skill.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        skill.description.toLowerCase().includes(searchTerm.toLowerCase())
      )
    : [];

  if (loading) {
    return <LoadingState />;
  }

  if (error) {
    return <ErrorState message={error} onRetry={refetch} />;
  }

  return (
    <div className="flex h-full overflow-hidden p-6 gap-6">
      {/* Sidebar Categories */}
      <div className="w-64 shrink-0 glass-card flex flex-col overflow-hidden">
        <div className="p-6 border-b border-slate-100">
          <h2 className="text-sm font-semibold flex items-center gap-2 uppercase tracking-widest text-slate-400">
            <BookOpen className="w-4 h-4 text-primary" />
            Library
          </h2>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-1">
          {skillsData && Object.keys(skillsData).map(category => (
            <button
              key={category}
              onClick={() => {
                setSelectedCategory(category);
                setSelectedSkill(null);
              }}
              className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all ${
                selectedCategory === category
                  ? 'bg-primary/10 text-primary'
                  : 'hover:bg-slate-50 text-slate-500 hover:text-slate-900'
              }`}
            >
              {getCategoryIcon(category)}
              <span className="capitalize">{category}</span>
              <span className={`ml-auto text-[10px] px-2 py-0.5 rounded-full border ${
                selectedCategory === category ? 'border-primary/20 bg-primary/10 text-cyan-800' : 'border-slate-100 bg-slate-50'
              }`}>
                {skillsData[category].length}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {selectedSkill ? (
          /* Skill Detail View */
          <div className="flex-1 glass-card flex flex-col overflow-hidden">
            <div className="p-6 border-b border-slate-200 flex items-center gap-4 bg-white">
              <button
                onClick={() => setSelectedSkill(null)}
                aria-label="Back to skill list"
                className="p-2 hover:bg-slate-100 rounded-xl transition-all border border-slate-200"
              >
                <ChevronRight className="w-5 h-5 rotate-180" />
              </button>
              <div className="flex-1">
                <span className="text-[10px] uppercase tracking-widest text-primary font-bold">Skill Detail</span>
                <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{selectedSkill.name}</h1>
              </div>
              <div className="flex items-center gap-3 px-4 py-2 bg-slate-50 rounded-xl border border-slate-200">
                <span className="text-xs font-semibold text-slate-600">Active in {currentGroup}</span>
                <Toggle
                  checked={isSkillActive(selectedSkill.id)}
                  onChange={(e) => toggleResource('skills', selectedSkill.id, e)}
                  aria-label={isSkillActive(selectedSkill.id) ? 'Deactivate skill' : 'Activate skill'}
                />
              </div>
            </div>
            <div className="flex-1 overflow-y-auto p-8 bg-white prose prose-slate max-w-none prose-headings:text-slate-900 prose-p:text-slate-700 prose-li:text-slate-700 prose-strong:text-slate-900">
              <ReactMarkdown
                components={{
                  code({className, children, ...props}) {
                    const isCodeBlock = className && className.startsWith('language-');
                    return isCodeBlock ? (
                      <code className={`${className} font-mono`} {...props}>
                        {children}
                      </code>
                    ) : (
                      <code className="font-mono bg-slate-100 border border-slate-200 px-1.5 py-0.5 rounded text-cyan-700 text-[0.875em]" {...props}>
                        {children}
                      </code>
                    );
                  },
                  pre({children, ...props}) {
                    return (
                      <pre className="!bg-slate-900 !text-slate-100 p-5 rounded-xl shadow-inner border border-slate-700 overflow-x-auto" {...props}>
                        {children}
                      </pre>
                    )
                  }
                }}
              >
                {selectedSkill.readme}
              </ReactMarkdown>
            </div>
          </div>
        ) : (
          /* Skill List View */
          <div className="flex-1 flex flex-col overflow-hidden gap-6">
            <div className="p-6 glass-card bg-slate-50/30 backdrop-blur-sm">
              <div className="relative max-w-md">
                <label htmlFor="skill-search" className="sr-only">Search skills</label>
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  id="skill-search"
                  type="text"
                  placeholder="Search skills..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full pl-10 pr-4 py-3 bg-white border border-slate-100 rounded-xl focus:outline-none focus:ring-1 focus:ring-primary/20 focus:border-primary/30 transition-all text-sm placeholder:text-slate-400"
                />
              </div>
            </div>
            <div className="flex-1 overflow-y-auto pr-2">
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {filteredSkills.map(skill => (
                  <div
                    key={skill.id}
                    onClick={() => setSelectedSkill(skill)}
                    className={`group glass-card p-6 hover:border-primary/20 hover:bg-slate-50/50 transition-all cursor-pointer relative overflow-hidden ${
                      !isSkillActive(skill.id) ? 'bg-slate-50/60 border-slate-200' : ''
                    }`}
                  >
                    <div className="flex justify-between items-start mb-4">
                      <div className={`p-2 rounded-lg ${isSkillActive(skill.id) ? 'bg-primary/10 text-primary' : 'bg-slate-100 text-slate-400'}`}>
                        <Terminal className="w-5 h-5" />
                      </div>

                      <Toggle
                        checked={isSkillActive(skill.id)}
                        onChange={(e) => toggleResource('skills', skill.id, e)}
                        aria-label={`Toggle ${skill.name} active status`}
                      />
                    </div>

                    <h2 className="break-words text-lg font-semibold tracking-tight group-hover:text-primary transition-colors mb-2">
                      {skill.name}
                    </h2>
                    <p className="text-sm text-slate-500 line-clamp-3 font-medium leading-relaxed">
                      {skill.description}
                    </p>
                    <div className="mt-6 flex items-center text-[11px] font-semibold uppercase tracking-wider text-primary/60 group-hover:text-primary transition-all group-hover:translate-x-1">
                      View details <ChevronRight className="w-3 h-3 ml-1" />
                    </div>

                    <div className={`absolute top-0 right-0 w-1 h-full transition-all ${
                      isSkillActive(skill.id) ? 'bg-primary' : 'bg-slate-200'
                    }`} />
                  </div>
                ))}
              </div>
              {filteredSkills.length === 0 && (
                <div className="text-center py-20 text-slate-400 glass-card">
                  No skills found in this category.
                </div>
              )}
            </div>
          </div>
        )}
      </div>
      {toggleError && (
        <div className="fixed bottom-4 right-4 p-4 bg-red-50 border border-red-200 text-red-600 rounded-xl text-sm font-medium shadow-lg">
          {toggleError}
        </div>
      )}
    </div>
  );
};

export default SkillGallery;
