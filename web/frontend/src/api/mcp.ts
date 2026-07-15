export interface McpServer {
  name: string;
  scope: 'project' | 'global';
  transport: string;
  command: string[] | null;
  url: string | null;
  env: Record<string, string>;
}

import request from '../utils/request';

export interface AddMcpServerParams {
  project: string;
  name: string;
  command?: string[];
  url?: string;
  env?: Record<string, string>;
  transport?: string;
}

export async function fetchMcpServers(engine: string, project: string): Promise<McpServer[]> {
  return request(
    `/api/mcp/${encodeURIComponent(engine)}?project=${encodeURIComponent(project)}`,
  );
}

export async function addMcpServer(engine: string, params: AddMcpServerParams): Promise<void> {
  await request(`/api/mcp/${encodeURIComponent(engine)}`, {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

export async function removeMcpServer(
  engine: string,
  name: string,
  project: string,
): Promise<void> {
  await request(
    `/api/mcp/${encodeURIComponent(engine)}/${encodeURIComponent(name)}?project=${encodeURIComponent(project)}`,
    { method: 'DELETE' },
  );
}
