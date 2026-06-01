'use client';

import { useState } from 'react';
import { evalQuery } from '@/lib/api';

const EXAMPLE = `define X on custID:
  compute A on Age transformedby 'aggregate:any'
  compute G on Gender transformedby 'aggregate:any'
  compute N on Comment transformedby 'map:python,,len($N$);aggregate:sum'
  output A,G,N
  where True`;

interface Props {
  projectId: string;
}

type ResultFormat = 'json' | 'csv';

interface QueryEditor {
  id: number;
  title: string;
  query: string;
  result: string;
  error: string | null;
  format: ResultFormat | null;
}

const createEditor = (id: number, query = ''): QueryEditor => ({
  id,
  title: `Query ${id}`,
  query,
  result: '',
  error: null,
  format: null,
});

export default function QueryBuilder({ projectId }: Props) {
  const [editors, setEditors] = useState<QueryEditor[]>([createEditor(1, EXAMPLE)]);
  const [activeId, setActiveId] = useState(1);
  const [nextId, setNextId] = useState(2);
  const [loading, setLoading] = useState(false);
  const [runningFormat, setRunningFormat] = useState<ResultFormat | null>(null);

  const activeEditor = editors.find(editor => editor.id === activeId) ?? editors[0];

  const updateActiveEditor = (updates: Partial<QueryEditor>) => {
    setEditors(prev => prev.map(editor => (
      editor.id === activeEditor.id ? { ...editor, ...updates } : editor
    )));
  };

  const addEditor = () => {
    const editor = createEditor(nextId);
    setEditors(prev => [...prev, editor]);
    setActiveId(editor.id);
    setNextId(prev => prev + 1);
  };

  const closeEditor = (id: number) => {
    if (editors.length === 1) return;
    const index = editors.findIndex(editor => editor.id === id);
    const remaining = editors.filter(editor => editor.id !== id);
    setEditors(remaining);
    if (activeId === id) {
      const nextActive = remaining[Math.min(index, remaining.length - 1)];
      setActiveId(nextActive.id);
    }
  };

  const loadExample = () => {
    updateActiveEditor({
      query: EXAMPLE,
      result: '',
      error: null,
      format: null,
    });
  };

  const run = async (fmt: ResultFormat) => {
    const editorId = activeEditor.id;
    const query = activeEditor.query;
    setLoading(true);
    setRunningFormat(fmt);
    setEditors(prev => prev.map(editor => (
      editor.id === editorId
        ? { ...editor, result: '', error: null, format: fmt }
        : editor
    )));
    try {
      const result = await evalQuery(query, fmt, projectId);
      setEditors(prev => prev.map(editor => (
        editor.id === editorId ? { ...editor, result, error: null, format: fmt } : editor
      )));
    } catch (err) {
      setEditors(prev => prev.map(editor => (
        editor.id === editorId ? { ...editor, error: String(err), result: '', format: fmt } : editor
      )));
    } finally {
      setLoading(false);
      setRunningFormat(null);
    }
  };

  return (
    <div className="flex gap-4">
      {/* Editor */}
      <div className="w-96 flex-shrink-0">
        <div className="card h-full flex flex-col">
          <div className="border-b border-gray-200">
            <div className="flex items-center gap-1 px-2 pt-2 overflow-x-auto">
              {editors.map(editor => (
                <button
                  key={editor.id}
                  type="button"
                  onClick={() => setActiveId(editor.id)}
                  className={[
                    'group flex items-center gap-2 max-w-36 px-3 py-1.5 text-xs border border-b-0 rounded-t bg-white',
                    editor.id === activeEditor.id
                      ? 'text-blue-700 border-blue-200 bg-blue-50'
                      : 'text-gray-600 border-gray-200 hover:bg-gray-50',
                  ].join(' ')}
                  title={editor.title}
                >
                  <span className="truncate">{editor.title}</span>
                  {editors.length > 1 && (
                    <span
                      role="button"
                      tabIndex={0}
                      onClick={event => {
                        event.stopPropagation();
                        closeEditor(editor.id);
                      }}
                      onKeyDown={event => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault();
                          event.stopPropagation();
                          closeEditor(editor.id);
                        }
                      }}
                      className="text-gray-400 hover:text-gray-700"
                      aria-label={`Close ${editor.title}`}
                    >
                      x
                    </span>
                  )}
                </button>
              ))}
              <button
                type="button"
                onClick={addEditor}
                className="h-7 w-7 flex items-center justify-center text-base text-gray-600 border border-gray-200 rounded hover:bg-gray-50"
                title="New query editor"
                aria-label="New query editor"
              >
                +
              </button>
            </div>
            <div className="card-header border-b-0">
              <span className="font-semibold text-sm text-gray-700">QDVM Query</span>
              <button
                onClick={loadExample}
                className="text-xs text-blue-600 hover:underline"
              >
                Load example
              </button>
            </div>
          </div>
          <div className="flex-1 p-2">
            <textarea
              value={activeEditor.query}
              onChange={e => updateActiveEditor({ query: e.target.value })}
              spellCheck={false}
              className="w-full h-72 p-2 text-xs font-mono bg-gray-50 border border-gray-200 rounded resize-y focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
          <div className="flex gap-2 px-2 pb-2">
            <button onClick={() => run('json')} disabled={loading} className="btn-primary">
              {loading && runningFormat === 'json' ? 'Running...' : 'Run to JSON'}
            </button>
            <button onClick={() => run('csv')} disabled={loading} className="btn-secondary">
              {loading && runningFormat === 'csv' ? 'Running...' : 'Run to CSV'}
            </button>
          </div>
        </div>
      </div>

      {/* Results */}
      <div className="flex-1 min-w-0">
        <div className="card h-full flex flex-col">
          <div className="card-header">
            <span className="font-semibold text-sm text-gray-700">Results</span>
            {activeEditor.result && !activeEditor.error && (
              <span className="badge-green">{activeEditor.format === 'csv' ? 'CSV' : 'JSON'}</span>
            )}
          </div>
          <div className="flex-1 p-2 overflow-auto">
            {activeEditor.error ? (
              <pre className="text-xs text-red-600 whitespace-pre-wrap break-all font-mono">{activeEditor.error}</pre>
            ) : (
              <pre className="text-xs text-gray-800 whitespace-pre-wrap break-all font-mono">
                {activeEditor.result || <span className="text-gray-400">Run a query to see results here.</span>}
              </pre>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
