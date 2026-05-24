'use client';

import { useState } from 'react';
import { addEdge } from '@/lib/api';
import type { EdgeInput } from '@/lib/types';

interface Props {
  onClose: () => void;
  onSaved: () => void;
}

const EMPTY: EdgeInput = {
  head: '', tail: '', datasource: '', key: '', value: '', query: '', selected: false,
};

export default function AddEdgeModal({ onClose, onSaved }: Props) {
  const [form, setForm] = useState<EdgeInput>(EMPTY);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const set = (field: keyof EdgeInput) =>
    (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm(prev => ({ ...prev, [field]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }));

  const handleSave = async () => {
    if (!form.head.trim() || !form.tail.trim() || !form.datasource.trim()) {
      setError('Head, tail, and datasource are required.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await addEdge(form);
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
          <h2 className="font-semibold text-gray-800">Add DVM Edge</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">&times;</button>
        </div>

        <div className="p-4 grid grid-cols-2 gap-3">
          <div>
            <label className="label">Head (parent) <span className="text-red-500">*</span></label>
            <input className="input" value={form.head} onChange={set('head')} placeholder="custID" />
          </div>
          <div>
            <label className="label">Tail (child) <span className="text-red-500">*</span></label>
            <input className="input" value={form.tail} onChange={set('tail')} placeholder="Age" />
          </div>
          <div className="col-span-2">
            <label className="label">Datasource <span className="text-red-500">*</span></label>
            <input className="input" value={form.datasource} onChange={set('datasource')} placeholder="customers_csv" />
          </div>
          <div>
            <label className="label">Key column(s)</label>
            <input className="input" value={form.key} onChange={set('key')} placeholder="1" />
          </div>
          <div>
            <label className="label">Value column(s)</label>
            <input className="input" value={form.value} onChange={set('value')} placeholder="2" />
          </div>
          <div className="col-span-2">
            <label className="label">SQL query (optional)</label>
            <input className="input" value={form.query} onChange={set('query')} placeholder="" />
          </div>
          <div className="col-span-2 flex items-center gap-2">
            <input
              type="checkbox"
              id="edge-sel"
              checked={!!form.selected}
              onChange={set('selected')}
              className="rounded border-gray-300 text-blue-600"
            />
            <label htmlFor="edge-sel" className="text-sm text-gray-700">
              Selected — include in exports
            </label>
          </div>
          {error && <p className="col-span-2 text-xs text-red-600">{error}</p>}
        </div>

        <div className="flex justify-end gap-2 px-4 py-3 border-t bg-gray-50 rounded-b-lg">
          <button onClick={onClose} className="btn-secondary">Cancel</button>
          <button onClick={handleSave} disabled={saving} className="btn-primary">
            {saving ? 'Adding…' : 'Add Edge'}
          </button>
        </div>
      </div>
    </div>
  );
}
