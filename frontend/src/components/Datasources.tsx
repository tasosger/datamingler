'use client';

import { useEffect, useState, useCallback } from 'react';
import { getDatasources, removeDatasource } from '@/lib/api';
import type { Datasource } from '@/lib/types';
import AddDatasourceModal from './AddDatasourceModal';

export default function Datasources() {
  const [sources, setSources]   = useState<Datasource[]>([]);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState<string | null>(null);
  const [showAdd, setShowAdd]   = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setSources(await getDatasources());
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleDelete = async (name: string) => {
    if (!confirm(`Delete datasource "${name}"?`)) return;
    try {
      await removeDatasource(name);
      await load();
    } catch (err) {
      alert('Failed to delete:\n' + err);
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-semibold text-gray-800">Datasources</h2>
        <button onClick={() => setShowAdd(true)} className="btn-primary">Add Datasource</button>
      </div>

      {loading && <p className="text-sm text-gray-500">Loading…</p>}
      {error   && <p className="text-sm text-red-600">{error}</p>}

      {!loading && !error && sources.length === 0 && (
        <p className="text-sm text-gray-500">No datasources defined.</p>
      )}

      {sources.length > 0 && (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-3 py-2 text-left font-medium text-gray-600">Name</th>
                <th className="px-3 py-2 text-left font-medium text-gray-600">Type</th>
                <th className="px-3 py-2 text-left font-medium text-gray-600">Options</th>
                <th className="px-3 py-2 w-24"></th>
              </tr>
            </thead>
            <tbody>
              {sources.map((s, i) => {
                const opts = Object.entries(s).filter(([k]) => k !== 'name' && k !== 'type');
                return (
                  <tr key={s.name} className={i % 2 === 0 ? '' : 'bg-gray-50'}>
                    <td className="px-3 py-2 font-medium text-gray-800">{s.name}</td>
                    <td className="px-3 py-2">
                      <span className="badge-blue">{s.type}</span>
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap gap-1">
                        {opts.map(([k, v]) => (
                          <span key={k} className="badge-gray">{k}: {v}</span>
                        ))}
                      </div>
                    </td>
                    <td className="px-3 py-2 text-right">
                      <button
                        onClick={() => handleDelete(s.name)}
                        className="text-xs text-red-600 hover:text-red-800 hover:underline"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {showAdd && (
        <AddDatasourceModal
          onClose={() => setShowAdd(false)}
          onSaved={async () => { setShowAdd(false); await load(); }}
        />
      )}
    </div>
  );
}
