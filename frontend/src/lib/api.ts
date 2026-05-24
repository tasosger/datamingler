// All paths go through /api/* which Next.js proxies to the Python server.
import type { DVMEdge, DVMGraph, Datasource, EdgeInput, DatasourceInput } from './types';

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

// ── DVM graph ──────────────────────────────────────────────────────────────

export function getDVM(): Promise<DVMGraph> {
  return request<DVMGraph>('/dvm');
}

export function addEdge(edge: EdgeInput): Promise<void> {
  return request('/dvm/edge', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(edge),
  });
}

export function updateEdge(
  head: string,
  tail: string,
  updates: Partial<Pick<DVMEdge, 'selected' | 'datasource' | 'query' | 'description'>>,
): Promise<void> {
  return request('/dvm/edge', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ head, tail, ...updates }),
  });
}

export function deleteEdge(head: string, tail: string): Promise<void> {
  return request(
    `/dvm/edge?head=${encodeURIComponent(head)}&tail=${encodeURIComponent(tail)}`,
    { method: 'DELETE' },
  );
}

// ── Datasources ────────────────────────────────────────────────────────────

export function getDatasources(): Promise<Datasource[]> {
  return request<Datasource[]>('/datasources');
}

export function addDatasource(ds: DatasourceInput): Promise<void> {
  return request('/datasources', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(ds),
  });
}

export function removeDatasource(name: string): Promise<void> {
  return request(`/datasources/${encodeURIComponent(name)}`, { method: 'DELETE' });
}

// ── Query evaluation ───────────────────────────────────────────────────────

export async function evalQuery(
  queryText: string,
  format: 'json' | 'csv',
): Promise<string> {
  const endpoint = format === 'csv' ? '/eval-csv' : '/eval';
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
