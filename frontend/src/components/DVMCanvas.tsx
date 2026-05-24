'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import type { Core, ElementDefinition, EventObject } from 'cytoscape';
import type { DVMEdge, DVMGraph } from '@/lib/types';
import { getDVM, deleteEdge, updateEdge } from '@/lib/api';
import EdgeSidebar from './EdgeSidebar';
import AddEdgeModal from './AddEdgeModal';

// Typed as any[] because @types/cytoscape distinguishes StylesheetStyle (style key)
// from StylesheetCSS (css key) and doesn't export a union-friendly type.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const CY_STYLE: any[] = [
  {
    selector: 'node',
    style: {
      'background-color': '#6ea8fe',
      'border-color': '#3d8bfd',
      'border-width': 2,
      label: 'data(label)',
      color: '#1a1a2e',
      'text-valign': 'center',
      'text-halign': 'center',
      'font-size': '11px',
      'font-weight': '600',
      width: 70,
      height: 70,
    },
  },
  {
    selector: 'edge[!dvmSelected]',
    style: {
      width: 2,
      'line-color': '#adb5bd',
      'target-arrow-color': '#adb5bd',
      'target-arrow-shape': 'triangle',
      'curve-style': 'bezier',
      label: 'data(label)',
      'font-size': '9px',
      color: '#6c757d',
      'text-background-color': '#fff',
      'text-background-opacity': 0.8,
      'text-background-padding': '2px',
    },
  },
  {
    selector: 'edge[?dvmSelected]',
    style: {
      width: 3,
      'line-color': '#198754',
      'target-arrow-color': '#198754',
      'target-arrow-shape': 'triangle',
      'curve-style': 'bezier',
      label: 'data(label)',
      'font-size': '9px',
      color: '#146c43',
      'text-background-color': '#fff',
      'text-background-opacity': 0.8,
      'text-background-padding': '2px',
    },
  },
  {
    selector: 'edge:selected',
    style: { 'line-color': '#fd7e14', 'target-arrow-color': '#fd7e14', width: 4 },
  },
];

function graphToElements(data: DVMGraph): ElementDefinition[] {
  const els: ElementDefinition[] = [];
  for (const node of data.nodes) {
    els.push({ data: { id: node.name, label: node.name, description: node.description } });
  }
  data.edges.forEach((e, idx) => {
    els.push({
      data: {
        id: `${e.head}--${e.tail}--${idx}`,
        source: e.head,
        target: e.tail,
        label: e.datasource,
        dvmHead: e.head,
        dvmTail: e.tail,
        dvmDatasource: e.datasource,
        dvmQuery: e.query,
        dvmKey: e.key,
        dvmValue: e.value,
        dvmSelected: e.selected,
        dvmDescription: e.description,
      },
    });
  });
  return els;
}

export default function DVMCanvas() {
  const containerRef  = useRef<HTMLDivElement>(null);
  const cyRef         = useRef<Core | null>(null);
  const [graph, setGraph]         = useState<DVMGraph | null>(null);
  const [activeEdge, setActiveEdge] = useState<DVMEdge | null>(null);
  const [showAdd, setShowAdd]     = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const loadGraph = useCallback(async () => {
    try {
      setGraph(await getDVM());
      setLoadError(null);
    } catch (err) {
      setLoadError(String(err));
    }
  }, []);

  useEffect(() => { loadGraph(); }, [loadGraph]);

  // Build / rebuild Cytoscape whenever graph data changes
  useEffect(() => {
    if (!graph || !containerRef.current) return;

    let cancelled = false;

    import('cytoscape').then(({ default: cytoscape }) => {
      if (cancelled || !containerRef.current) return;
      if (cyRef.current) { cyRef.current.destroy(); cyRef.current = null; }

      const cy = cytoscape({
        container: containerRef.current,
        elements: graphToElements(graph),
        style: CY_STYLE,
        layout: { name: 'cose', padding: 40, animate: false },
      });

      cy.on('tap', 'edge', (evt: EventObject) => {
        const d = (evt.target as ReturnType<Core['$']>).data();
        setActiveEdge({
          head: d.dvmHead, tail: d.dvmTail,
          head_description: '', tail_description: '',
          datasource: d.dvmDatasource, query: d.dvmQuery,
          key: d.dvmKey, value: d.dvmValue,
          selected: d.dvmSelected, description: d.dvmDescription,
        });
      });

      cy.on('tap', (evt: EventObject) => {
        if (evt.target === cy) setActiveEdge(null);
      });

      cyRef.current = cy;
    });

    return () => { cancelled = true; };
  }, [graph]);

  const handleToggle = async (edge: DVMEdge) => {
    try {
      await updateEdge(edge.head, edge.tail, { selected: !edge.selected });
      setActiveEdge(null);
      await loadGraph();
    } catch (err) {
      alert('Failed to update edge:\n' + err);
    }
  };

  const handleDelete = async () => {
    if (!activeEdge) return;
    if (!confirm(`Delete edge ${activeEdge.head} → ${activeEdge.tail}?`)) return;
    try {
      await deleteEdge(activeEdge.head, activeEdge.tail);
      setActiveEdge(null);
      await loadGraph();
    } catch (err) {
      alert('Failed to delete edge:\n' + err);
    }
  };

  return (
    <div className="flex gap-4">
      {/* Graph panel */}
      <div className="flex-1 min-w-0">
        <div className="card">
          <div className="card-header">
            <span className="font-semibold text-sm text-gray-700">DVM Graph</span>
            <div className="flex gap-2">
              <button onClick={() => setShowAdd(true)} className="btn-primary">Add Edge</button>
              <button onClick={handleDelete} disabled={!activeEdge} className="btn-danger">
                Delete Selected
              </button>
              <button onClick={loadGraph} className="btn-secondary" title="Refresh">&#8635;</button>
            </div>
          </div>
          {loadError && (
            <div className="px-3 py-2 text-sm text-red-600 bg-red-50 border-b border-red-200">
              {loadError}
            </div>
          )}
          <div ref={containerRef} style={{ height: 560, background: '#f8fafc' }} />
        </div>
      </div>

      {/* Sidebar */}
      <div className="w-60 flex-shrink-0 flex flex-col gap-3">
        {activeEdge && (
          <EdgeSidebar
            edge={activeEdge}
            onToggleSelected={handleToggle}
            onClose={() => setActiveEdge(null)}
          />
        )}
        <div className="card p-3 text-sm">
          <p className="font-semibold text-gray-700 mb-2.5">Legend</p>
          {[
            { color: '#6ea8fe', label: 'Attribute node' },
            { color: '#198754', label: 'Selected edge' },
            { color: '#adb5bd', label: 'Unselected edge' },
          ].map(({ color, label }) => (
            <div key={label} className="flex items-center gap-2 mb-1.5">
              <span className="w-4 h-2 rounded-sm flex-shrink-0" style={{ background: color }} />
              <span className="text-gray-600">{label}</span>
            </div>
          ))}
        </div>
      </div>

      {showAdd && (
        <AddEdgeModal
          onClose={() => setShowAdd(false)}
          onSaved={async () => { setShowAdd(false); await loadGraph(); }}
        />
      )}
    </div>
  );
}
