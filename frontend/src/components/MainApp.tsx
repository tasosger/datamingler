'use client';

import { useEffect, useState } from 'react';
import Navbar from './Navbar';
import DVMCanvas from './DVMCanvas';
import QueryBuilder from './QueryBuilder';
import Datasources from './Datasources';
import { getProjects, addProject } from '@/lib/api';
import type { Project } from '@/lib/types';

type Tab = 'dvm' | 'query' | 'sources';

const TABS: { id: Tab; label: string }[] = [
  { id: 'dvm',     label: 'DVM Canvas' },
  { id: 'query',   label: 'Query Builder' },
  { id: 'sources', label: 'Datasources' },
];

export default function MainApp() {
  const [activeTab, setActiveTab] = useState<Tab>('dvm');
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState('default');
  const [projectError, setProjectError] = useState<string | null>(null);

  const loadProjects = async () => {
    try {
      const items = await getProjects();
      setProjects(items);
      if (!items.some(project => project.id === projectId) && items[0]) setProjectId(items[0].id);
      setProjectError(null);
    } catch (err) {
      setProjectError(String(err));
    }
  };

  useEffect(() => { loadProjects(); }, []);

  const createProject = async () => {
    const name = prompt('Project name');
    if (!name) return;
    const id = name.trim().toLowerCase().replace(/[^a-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '');
    if (!id) return;
    try {
      const project = await addProject({ id, name: name.trim() });
      await loadProjects();
      setProjectId(project.id);
    } catch (err) {
      alert('Failed to create project:\n' + err);
    }
  };

  return (
    <div className="flex flex-col min-h-screen">
      <Navbar />

      <div className="px-4 pt-4 pb-6 flex-1">
        <div className="flex items-center justify-between gap-3 mb-4">
          <div>
            <label className="label">Project</label>
            <select
              className="select min-w-56"
              value={projectId}
              onChange={event => setProjectId(event.target.value)}
            >
              {projects.map(project => (
                <option key={project.id} value={project.id}>{project.name}</option>
              ))}
            </select>
          </div>
          <button onClick={createProject} className="btn-secondary">New Project</button>
        </div>
        {projectError && <p className="text-sm text-red-600 mb-3">{projectError}</p>}

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
          <DVMCanvas projectId={projectId} />
        </div>
        <div className={activeTab === 'query' ? '' : 'hidden'}>
          <QueryBuilder projectId={projectId} />
        </div>
        <div className={activeTab === 'sources' ? '' : 'hidden'}>
          <Datasources projectId={projectId} />
        </div>
      </div>
    </div>
  );
}
