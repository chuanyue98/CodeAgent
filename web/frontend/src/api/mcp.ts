export interface McpServer {
  name: string;
  scope: 'project' | 'global';
  transport: string;
  command: string[] | null;
  url: string | null;
  env: Record<string, string>;
}

export interface AddMcpServerParams {
  project: string;
  name: string;
  command?: string[];
  url?: string;
  env?: Record<string, string>;
  transport?: string;
}

async function handleResponse<T>(res: Response, fallbackMessage: string): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || fallbackMessage);
  }
  return res.json();
}

export async function fetchMcpServers(engine: string, project: string): Promise<McpServer[]> {
  const res = await fetch(
    `/api/mcp/${encodeURIComponent(engine)}?project=${encodeURIComponent(project)}`,
  );
  return handleResponse(res, 'Failed to fetch MCP servers');
}

export async function addMcpServer(engine: string, params: AddMcpServerParams): Promise<void> {
  const res = await fetch(`/api/mcp/${encodeURIComponent(engine)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  await handleResponse(res, 'Failed to add MCP server');
}

export async function removeMcpServer(
  engine: string,
  name: string,
  project: string,
): Promise<void> {
  const res = await fetch(
    `/api/mcp/${encodeURIComponent(engine)}/${encodeURIComponent(name)}?project=${encodeURIComponent(project)}`,
    { method: 'DELETE' },
  );
  await handleResponse(res, 'Failed to remove MCP server');
}
