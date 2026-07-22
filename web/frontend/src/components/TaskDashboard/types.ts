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
  task_id: string;
  engine: string;
  status: 'running' | 'completed' | 'failed' | 'stopped';
  log_path: string;
  start_time: number;
  workspace?: string;
}

export interface Task {
  name: string;
  title: string;
  description: string;
  hasStages: boolean;
  stages: Stage[];
  content?: string;
  resolved_skills?: Skill[];
  resolved_prompts?: string[];
  logs?: string;
}

export interface RunPollResponse {
  status: RunStatus;
  progress: Partial<Task>;
}

export const STATUS_DONE = ['已完成', 'DONE', '无需修改'];
export const STATUS_WIP = ['进行中', 'IN_PROGRESS', '等待 CI 中', 'PR 审核中', 'IN PROGRESS'];

export const NAME_PATTERN = /^[\w.-]+$/;
