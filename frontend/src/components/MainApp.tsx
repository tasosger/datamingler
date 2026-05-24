'use client';

import { useState } from 'react';
import Navbar from './Navbar';
import DVMCanvas from './DVMCanvas';
import QueryBuilder from './QueryBuilder';
import Datasources from './Datasources';

type Tab = 'dvm' | 'query' | 'sources';

const TABS: { id: Tab; label: string }[] = [
  { id: 'dvm',     label: 'DVM Canvas' },
  { id: 'query',   label: 'Query Builder' },
  { id: 'sources', label: 'Datasources' },
];

export default function MainApp() {
  const [activeTab, setActiveTab] = useState<Tab>('dvm');

  return (
    <div className="flex flex-col min-h-screen">
      <Navbar />

      <div className="px-4 pt-4 pb-6 flex-1">
        {/* Tab bar */}
        <div className="border-b border-gray-200 mb-4">
          <nav className="-mb-px flex gap-1" aria-label="Tabs">
            {TABS.map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={[
                  'px-4 py-2 text-sm font-medium border-b-2 transition-colors focus-visible:outline-none',
                  activeTab === tab.id
                    ? 'border-blue-600 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300',
                ].join(' ')}
              >
                {tab.label}
              </button>
            ))}
          </nav>
        </div>

        {/* Tab panels */}
        <div className={activeTab === 'dvm' ? '' : 'hidden'}>
          <DVMCanvas />
        </div>
        <div className={activeTab === 'query' ? '' : 'hidden'}>
          <QueryBuilder />
        </div>
        <div className={activeTab === 'sources' ? '' : 'hidden'}>
          <Datasources />
        </div>
      </div>
    </div>
  );
}
