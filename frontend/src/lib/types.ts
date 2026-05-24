export interface AttributeNode {
  name: string;
  description: string;
}

export interface DVMEdge {
  head: string;
  tail: string;
  head_description: string;
  tail_description: string;
  datasource: string;
  query: string;
  key: string;
  value: string;
  selected: boolean;
  description: string;
}

export interface DVMGraph {
  nodes: AttributeNode[];
  edges: DVMEdge[];
}

export type DatasourceType = 'csv' | 'excel' | 'db' | 'process';

export interface Datasource {
  name: string;
  type: DatasourceType | string;
  [key: string]: string;
}

export interface EdgeInput {
  head: string;
  tail: string;
  datasource: string;
  key?: string;
  value?: string;
  query?: string;
  selected?: boolean;
  head_description?: string;
  tail_description?: string;
}

export interface DatasourceInput {
  name: string;
  type: DatasourceType;
  [key: string]: string;
}
