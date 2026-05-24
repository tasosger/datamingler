import type { DVMEdge } from '@/lib/types';

interface Props {
  edge: DVMEdge;
  onToggleSelected: (edge: DVMEdge) => void;
  onClose: () => void;
}

export default function EdgeSidebar({ edge, onToggleSelected, onClose }: Props) {
  const rows: [string, string][] = [
    ['Head', edge.head],
    ['Tail', edge.tail],
    ['Datasource', edge.datasource || '—'],
    ['Key col', edge.key || '—'],
    ['Value col', edge.value || '—'],
    ['SQL query', edge.query || '—'],
  ];

  return (
    <div className="card">
      <div className="card-header">
        <span className="font-semibold text-sm text-gray-700">Edge Details</span>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-lg leading-none">&times;</button>
      </div>
      <div className="p-3">
        <table className="w-full text-xs mb-3">
          <tbody>
            {rows.map(([k, v]) => (
              <tr key={k} className="border-b border-gray-100 last:border-0">
                <th className="py-1 pr-2 text-left font-medium text-gray-500 w-20">{k}</th>
                <td className="py-1 text-gray-800 break-all">{v}</td>
              </tr>
            ))}
            <tr>
              <th className="py-1 pr-2 text-left font-medium text-gray-500">Selected</th>
              <td className="py-1">
                {edge.selected
                  ? <span className="badge-green">yes</span>
                  : <span className="badge-gray">no</span>}
              </td>
            </tr>
          </tbody>
        </table>

        <button
          onClick={() => onToggleSelected(edge)}
          className={edge.selected ? 'btn-secondary w-full' : 'btn-success-outline w-full'}
        >
          {edge.selected ? 'Deselect edge' : 'Select edge'}
        </button>
      </div>
    </div>
  );
}
