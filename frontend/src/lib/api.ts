import type { DVMEdge, DVMGraph, Datasource, EdgeInput, DatasourceInput, Project } from './types';

const BASE = '/api';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    const msg = await res.text().catch(() => `HTTP ${res.status}`);
    throw new Error(msg || `HTTP ${res.status}`);
  }
  const ct = res.headers.get('content-type') ?? '';
  if (ct.includes('application/json')) return res.json() as Promise<T>;
  return res.text() as unknown as Promise<T>;
}

function projectPath(projectId: string | undefined, path: string): string {
  const id = projectId || 'default';
  return `/projects/${encodeURIComponent(id)}${path}`;
}

export function getProjects(): Promise<Project[]> {
  return request<Project[]>('/projects');
}

export function addProject(project: Pick<Project, 'id' | 'name'> & Partial<Project>): Promise<Project> {
  return request<Project>('/projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(project),
  });
}

export function getDVM(projectId?: string): Promise<DVMGraph> {
  return request<DVMGraph>(projectPath(projectId, '/dvm'));
}

export function addEdge(edge: EdgeInput, projectId?: string): Promise<void> {
  return request(projectPath(projectId, '/dvm/edge'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(edge),
  });
}

export function updateEdge(
  head: string,
  tail: string,
  updates: Partial<Pick<DVMEdge, 'selected' | 'datasource' | 'query' | 'description'>>,
  projectId?: string,
): Promise<void> {
  return request(projectPath(projectId, '/dvm/edge'), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ head, tail, ...updates }),
  });
}

export function deleteEdge(head: string, tail: string, projectId?: string): Promise<void> {
  return request(
    `${projectPath(projectId, '/dvm/edge')}?head=${encodeURIComponent(head)}&tail=${encodeURIComponent(tail)}`,
    { method: 'DELETE' },
  );
}

export function getDatasources(projectId?: string): Promise<Datasource[]> {
  return request<Datasource[]>(projectPath(projectId, '/datasources'));
}

export function addDatasource(ds: DatasourceInput, projectId?: string): Promise<void> {
  return request(projectPath(projectId, '/datasources'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(ds),
  });
}

export function uploadDatasourceFile(file: File, projectId?: string): Promise<{ path: string; filename: string }> {
  const endpoint = `${projectPath(projectId, '/files')}?filename=${encodeURIComponent(file.name)}`;
  return request<{ path: string; filename: string }>(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': file.type || 'application/octet-stream' },
    body: file,
  });
}

export function removeDatasource(name: string, projectId?: string): Promise<void> {
  return request(projectPath(projectId, `/datasources/${encodeURIComponent(name)}`), { method: 'DELETE' });
}

export interface AgentStep {
  name: string;
  status: string;
  detail: string;
  data?: Record<string, unknown> | null;
}

export interface AgentQuery {
  title: string;
  query: string;
  result: string;
  error: string;
}

export interface QueryAgentResponse {
  answer: string;
  provider: 'openai' | 'anthropic';
  model: string;
  queries: AgentQuery[];
  steps: AgentStep[];
}

export interface AgentMessage {
  role: 'user' | 'assistant' | string;
  content: string;
  created_at: string;
  provider?: string;
  model?: string;
  steps?: AgentStep[];
  queries?: AgentQuery[];
}

export interface AgentSession {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  provider: 'openai' | 'anthropic' | string;
  model: string;
  messages: AgentMessage[];
  message_count?: number;
}

export function getAgentSessions(projectId?: string): Promise<AgentSession[]> {
  return request<AgentSession[]>(projectPath(projectId, '/agent-sessions'));
}

export function createAgentSession(
  provider: 'openai' | 'anthropic',
  model: string,
  projectId?: string,
): Promise<AgentSession> {
  return request<AgentSession>(projectPath(projectId, '/agent-sessions'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider, model }),
  });
}

export function getAgentSession(sessionId: string, projectId?: string): Promise<AgentSession> {
  return request<AgentSession>(projectPath(projectId, `/agent-sessions/${encodeURIComponent(sessionId)}`));
}

export function sendAgentSessionMessage(
  sessionId: string,
  prompt: string,
  provider: 'openai' | 'anthropic',
  model: string,
  projectId?: string,
): Promise<AgentSession> {
  return request<AgentSession>(projectPath(projectId, `/agent-sessions/${encodeURIComponent(sessionId)}/messages`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt, provider, model }),
  });
}

export function runQueryAgent(
  prompt: string,
  provider: 'openai' | 'anthropic',
  model: string,
  projectId?: string,
): Promise<QueryAgentResponse> {
  return request<QueryAgentResponse>(projectPath(projectId, '/query/agent'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt, provider, model }),
  });
}

export async function evalQuery(
  queryText: string,
  format: 'json' | 'csv',
  projectId?: string,
): Promise<string> {
  const endpoint = projectPath(projectId, format === 'csv' ? '/eval-csv' : '/eval');
  const res = await fetch(`${BASE}${endpoint}`, {
    method: 'POST',
    headers: { 'Content-Type': 'text/plain' },
    body: queryText,
  });
  if (!res.ok) throw new Error(await res.text());
  if (format === 'json') {
    const data = await res.json();
    return JSON.stringify(data, null, 2);
  }
  return res.text();
}
