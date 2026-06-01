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

export default function QueryBuilder({ projectId }: Props) {
  const [query, setQuery]     = useState(EXAMPLE);
  const [result, setResult]   = useState('');
  const [error, setError]     = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [format, setFormat]   = useState<'json' | 'csv' | null>(null);

  const run = async (fmt: 'json' | 'csv') => {
    setLoading(true);
    setError(null);
    setResult('');
    setFormat(fmt);
    try {
      setResult(await evalQuery(query, fmt, projectId));
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex gap-4">
      {/* Editor */}
      <div className="w-96 flex-shrink-0">
        <div className="card h-full flex flex-col">
          <div className="card-header">
            <span className="font-semibold text-sm text-gray-700">QDVM Query</span>
            <button
              onClick={() => setQuery(EXAMPLE)}
              className="text-xs text-blue-600 hover:underline"
            >
              Load example
            </button>
          </div>
          <div className="flex-1 p-2">
            <textarea
              value={query}
              onChange={e => setQuery(e.target.value)}
              spellCheck={false}
              className="w-full h-72 p-2 text-xs font-mono bg-gray-50 border border-gray-200 rounded
                         resize-y focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
          <div className="flex gap-2 px-2 pb-2">
            <button onClick={() => run('json')} disabled={loading} className="btn-primary">
              {loading && format === 'json' ? 'Running…' : 'Run → JSON'}
            </button>
            <button onClick={() => run('csv')} disabled={loading} className="btn-secondary">
              {loading && format === 'csv' ? 'Running…' : 'Run → CSV'}
            </button>
          </div>
        </div>
      </div>

      {/* Results */}
      <div className="flex-1 min-w-0">
        <div className="card h-full flex flex-col">
          <div className="card-header">
            <span className="font-semibold text-sm text-gray-700">Results</span>
            {result && !error && (
              <span className="badge-green">{format === 'csv' ? 'CSV' : 'JSON'}</span>
            )}
          </div>
          <div className="flex-1 p-2 overflow-auto">
            {error ? (
              <pre className="text-xs text-red-600 whitespace-pre-wrap break-all font-mono">{error}</pre>
            ) : (
              <pre className="text-xs text-gray-800 whitespace-pre-wrap break-all font-mono">
                {result || <span className="text-gray-400">Run a query to see results here.</span>}
              </pre>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
