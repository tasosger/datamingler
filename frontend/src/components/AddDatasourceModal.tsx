'use client';

import { useState } from 'react';
import { addDatasource } from '@/lib/api';
import type { DatasourceInput, DatasourceType } from '@/lib/types';

interface Props {
  projectId: string;
  onClose: () => void;
  onSaved: () => void;
}

const TYPE_FIELDS: Record<DatasourceType, { key: string; label: string; placeholder?: string; default?: string }[]> = {
  csv: [
    { key: 'path',      label: 'Directory path',  placeholder: '.' },
    { key: 'filename',  label: 'Filename',         placeholder: 'data.csv' },
    { key: 'delimiter', label: 'Delimiter',        default: ',' },
    { key: 'headings',  label: 'Has headings',     default: 'yes' },
  ],
  excel: [
    { key: 'path',     label: 'Directory path', placeholder: '.' },
    { key: 'filename', label: 'Filename',        placeholder: 'data.xlsx' },
    { key: 'sheet',    label: 'Sheet name',      placeholder: 'Sheet1 (optional)' },
  ],
  db: [
    { key: 'connection', label: 'Connection string', placeholder: 'sqlite:///path/to/db.sqlite' },
  ],
  process: [
    { key: 'system',    label: 'System command', placeholder: 'python generate.py' },
    { key: 'delimiter', label: 'Delimiter',       default: ',' },
  ],
};

export default function AddDatasourceModal({ projectId, onClose, onSaved }: Props) {
  const [name, setName]   = useState('');
  const [type, setType]   = useState<DatasourceType>('csv');
  const [opts, setOpts]   = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError]   = useState<string | null>(null);

  const handleTypeChange = (t: DatasourceType) => {
    setType(t);
    const defaults: Record<string, string> = {};
    for (const f of TYPE_FIELDS[t]) {
      if (f.default) defaults[f.key] = f.default;
    }
    setOpts(defaults);
  };

  const setOpt = (key: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setOpts(prev => ({ ...prev, [key]: e.target.value }));

  const handleSave = async () => {
    if (!name.trim()) { setError('Name is required.'); return; }
    setSaving(true);
    setError(null);
    try {
      const payload: DatasourceInput = { name: name.trim(), type, ...opts };
      await addDatasource(payload, projectId);
      onSaved();
    } catch (err) {
      setError(String(err));
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative bg-white rounded-lg shadow-xl w-full max-w-md mx-4">
        <div className="flex items-center justify-between px-4 py-3 border-b">
          <h2 className="font-semibold text-gray-800">Add Datasource</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">&times;</button>
        </div>

        <div className="p-4 grid grid-cols-2 gap-3">
          <div>
            <label className="label">Name <span className="text-red-500">*</span></label>
            <input className="input" value={name} onChange={e => setName(e.target.value)} placeholder="my_source" />
          </div>
          <div>
            <label className="label">Type</label>
            <select
              className="select"
              value={type}
              onChange={e => handleTypeChange(e.target.value as DatasourceType)}
            >
              <option value="csv">CSV</option>
              <option value="excel">Excel</option>
              <option value="db">Database</option>
              <option value="process">Process</option>
            </select>
          </div>

          {TYPE_FIELDS[type].map(f => (
            <div key={f.key} className={f.key === 'connection' || f.key === 'system' || f.key === 'filename' || f.key === 'path' ? 'col-span-2' : ''}>
              <label className="label">{f.label}</label>
              <input
                className="input"
                value={opts[f.key] ?? ''}
                onChange={setOpt(f.key)}
                placeholder={f.placeholder ?? f.default ?? ''}
              />
            </div>
          ))}

          {error && <p className="col-span-2 text-xs text-red-600">{error}</p>}
        </div>

        <div className="flex justify-end gap-2 px-4 py-3 border-t bg-gray-50 rounded-b-lg">
          <button onClick={onClose} className="btn-secondary">Cancel</button>
          <button onClick={handleSave} disabled={saving} className="btn-primary">
            {saving ? 'Adding…' : 'Add'}
          </button>
        </div>
      </div>
    </div>
  );
}
