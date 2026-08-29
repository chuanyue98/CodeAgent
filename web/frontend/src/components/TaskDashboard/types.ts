export interface Stage {
  name: string;
  status: string;
  goal: string;
}

export interface Skill {
  name: string;
  id: string;
  description: string;
  scripts: string[];
}

export interface Engine {
  id: string;
  name: string;
  description: string;
}

export interface RunStatus {
  taskId: string;
  engine: string;
  status: 'running' | 'completed' | 'failed' | 'stopped';
  logPath: string;
  startTime: number;
  workspace?: string;
  endTime?: number;
  exitCode?: number;
}

export interface Task {
  name: string;
  title: string;
  description: string;
  hasStages: boolean;
  stages: Stage[];
  content?: string;
  resolvedSkills?: Skill[];
  resolvedPrompts?: string[];
  logs?: string;
}

export interface RunPollResponse {
  status: RunStatus;
  progress: Partial<Task>;
}

export type StageState = 'done' | 'wip' | 'todo';

// Task files only carry a free-text status string (e.g. "**状态**: [进行中]"
// from the architect-planning/interview-model skills' plan template, or an
// author's own wording). Matching by keyword/substring instead of an exact
// whitelist means a stage still shows correctly when it's written as "已完成
// ✅", "Done", "Blocked — waiting on review", etc. rather than only the
// handful of exact phrases a previous run happened to produce.
//
// The Chinese here is data, not UI copy: these match what is written *inside a
// user's task file*, so they stay put regardless of the interface language —
// translating them would stop the parser recognizing existing files.
const NOT_STARTED_PATTERN = /(未开始|not\s*started|^todo$)/i;
const DONE_PATTERN = /(已完成|完成|done|complete|无需修改|closed|merged)/i;
const WIP_PATTERN = /(进行中|in[\s_-]?progress|等待|pending|blocked|阻塞|review|审核)/i;

export function classifyStageStatus(status: string): StageState {
  const trimmed = status.trim();
  if (!trimmed || NOT_STARTED_PATTERN.test(trimmed)) return 'todo';
  if (DONE_PATTERN.test(trimmed)) return 'done';
  if (WIP_PATTERN.test(trimmed)) return 'wip';
  // Any other non-empty, unrecognized status: treat as in-progress rather
  // than invisible -- a stage with *some* status has at least started.
  return 'wip';
}

export const NAME_PATTERN = /^[\w.-]+$/;
