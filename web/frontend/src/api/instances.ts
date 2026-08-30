import request from '../utils/request';

export type InstanceKind = 'chat' | 'terminal' | 'task';

export interface AgentInstance {
  kind: InstanceKind;
  id: string;
  engine: string;
  cwd: string;
  title: string | null;
  status: string;
  pid: number | null;
  startedAt: string;
  stoppable: boolean;
}

export async function fetchInstances(): Promise<AgentInstance[]> {
  const body = await request('/api/instances') as { instances: AgentInstance[] };
  return body.instances;
}

export function stopInstance(kind: InstanceKind, id: string): Promise<unknown> {
  return request(`/api/instances/${kind}/${encodeURIComponent(id)}/stop`, {
    method: 'POST',
  });
}
