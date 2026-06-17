'use client';

import { useEffect, useState } from 'react';
import {
  createAgentSession,
  evalQuery,
  getAgentSession,
  getAgentSessions,
  sendAgentSessionMessage,
  type AgentMessage,
  type AgentSession,
  type AgentStep,
} from '@/lib/api';

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
type Provider = 'openai' | 'anthropic';

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
  const [agentRunning, setAgentRunning] = useState(false);
  const [prompt, setPrompt] = useState('');
  const [provider, setProvider] = useState<Provider>('openai');
  const [model, setModel] = useState('gpt-5.1');
  const [sessions, setSessions] = useState<AgentSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string>('');
  const [activeSession, setActiveSession] = useState<AgentSession | null>(null);
  const [sessionLoading, setSessionLoading] = useState(false);
  const [promptError, setPromptError] = useState<string | null>(null);
  const [runningFormat, setRunningFormat] = useState<ResultFormat | null>(null);

  const activeEditor = editors.find(editor => editor.id === activeId) ?? editors[0];
  const latestAssistant = [...(activeSession?.messages ?? [])].reverse().find(message => message.role === 'assistant');
  const agentAnswer = latestAssistant?.content ?? '';
  const agentSteps = latestAssistant?.steps ?? [];

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

  const providerModels: Record<Provider, string[]> = {
    openai: ['gpt-5.1', 'gpt-5', 'gpt-5-mini'],
    anthropic: ['claude-sonnet-4-5', 'claude-opus-4-1', 'claude-haiku-4-5'],
  };

  const handleProviderChange = (value: Provider) => {
    setProvider(value);
    setModel(providerModels[value][0]);
  };

  const refreshSessions = async (selectId?: string) => {
    setSessionLoading(true);
    try {
      const items = await getAgentSessions(projectId);
      setSessions(items);
      const selected = selectId || activeSessionId || items[0]?.id || '';
      setActiveSessionId(selected);
      if (selected) {
        const full = await getAgentSession(selected, projectId);
        setActiveSession(full);
        if (full.provider === 'openai' || full.provider === 'anthropic') setProvider(full.provider);
        if (full.model) setModel(full.model);
      } else {
        setActiveSession(null);
      }
    } catch (err) {
      setPromptError(String(err));
    } finally {
      setSessionLoading(false);
    }
  };

  useEffect(() => {
    setActiveSessionId('');
    setActiveSession(null);
    refreshSessions('');
  }, [projectId]);

  const startSession = async () => {
    setPromptError(null);
    try {
      const session = await createAgentSession(provider, model.trim() || providerModels[provider][0], projectId);
      await refreshSessions(session.id);
    } catch (err) {
      setPromptError(String(err));
    }
  };

  const selectSession = async (sessionId: string) => {
    setActiveSessionId(sessionId);
    setPromptError(null);
    try {
      const session = await getAgentSession(sessionId, projectId);
      setActiveSession(session);
      if (session.provider === 'openai' || session.provider === 'anthropic') setProvider(session.provider);
      if (session.model) setModel(session.model);
    } catch (err) {
      setPromptError(String(err));
    }
  };

  const runAgent = async () => {
    if (!prompt.trim()) {
      setPromptError('Describe what you want the agent to query.');
      return;
    }
    if (!model.trim()) {
      setPromptError('Select or enter a model.');
      return;
    }
    setAgentRunning(true);
    setPromptError(null);
    try {
      let sessionId = activeSessionId;
      if (!sessionId) {
        const created = await createAgentSession(provider, model.trim(), projectId);
        sessionId = created.id;
        setActiveSessionId(sessionId);
      }
      const session = await sendAgentSessionMessage(sessionId, prompt, provider, model.trim(), projectId);
      setActiveSession(session);
      setSessions(prev => {
        const summary = { ...session, messages: [], message_count: session.messages.length };
        const without = prev.filter(item => item.id !== session.id);
        return [summary, ...without];
      });
      const assistant = [...session.messages].reverse().find(message => message.role === 'assistant');
      const queries = assistant?.queries ?? [];
      if (!queries.length) {
        setPromptError('The agent did not return an executable query.');
        return;
      }
      const firstId = nextId;
      const generated = queries.map((item, index) => ({
        ...createEditor(firstId + index, item.query),
        title: item.title || `Generated ${index + 1}`,
        result: item.result,
        error: item.error || null,
        format: 'json' as ResultFormat,
      }));
      setEditors(prev => [...prev, ...generated]);
      setActiveId(generated[0].id);
      setNextId(prev => prev + generated.length);
      setPrompt('');
    } catch (err) {
      setPromptError(String(err));
    } finally {
      setAgentRunning(false);
    }
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
          <div className="p-2 border-b border-gray-200">
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-xs font-semibold text-gray-700">Agent sessions</span>
              <button type="button" onClick={startSession} className="btn-secondary" disabled={sessionLoading}>
                New
              </button>
            </div>
            <div className="mb-3 max-h-24 overflow-auto rounded border border-gray-200 bg-white">
              {sessions.length ? sessions.map(session => (
                <button
                  key={session.id}
                  type="button"
                  onClick={() => selectSession(session.id)}
                  className={[
                    'block w-full truncate px-2 py-1.5 text-left text-xs',
                    session.id === activeSessionId ? 'bg-blue-50 text-blue-700' : 'text-gray-600 hover:bg-gray-50',
                  ].join(' ')}
                  title={session.title}
                >
                  {session.title}
                </button>
              )) : (
                <div className="px-2 py-2 text-xs text-gray-400">
                  {sessionLoading ? 'Loading sessions...' : 'No agent sessions yet.'}
                </div>
              )}
            </div>
            <label className="label">Agent chat</label>
            <textarea
              value={prompt}
              onChange={event => setPrompt(event.target.value)}
              className="w-full h-20 p-2 text-xs bg-gray-50 border border-gray-200 rounded resize-none focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
              placeholder="customers with age over 40, include gender and comment length"
            />
            <div className="mt-2 grid grid-cols-2 gap-2">
              <select
                className="select"
                value={provider}
                onChange={event => handleProviderChange(event.target.value as Provider)}
              >
                <option value="openai">OpenAI</option>
                <option value="anthropic">Claude</option>
              </select>
              <input
                className="input"
                value={model}
                onChange={event => setModel(event.target.value)}
                list="llm-models"
              />
              <datalist id="llm-models">
                {providerModels[provider].map(item => (
                  <option key={item} value={item} />
                ))}
              </datalist>
            </div>
            <div className="mt-2 flex items-center justify-between gap-2">
              <button
                type="button"
                onClick={runAgent}
                disabled={agentRunning}
                className="btn-secondary"
              >
                {agentRunning ? 'Running agent...' : 'Send to agent'}
              </button>
              {promptError && <span className="text-xs text-red-600 truncate">{promptError}</span>}
            </div>
            {(agentAnswer || agentSteps.length > 0) && (
              <div className="mt-3 space-y-2">
                {activeSession && activeSession.messages.length > 0 && (
                  <div className="rounded border border-gray-200 bg-white">
                    <div className="px-2 py-1 text-xs font-semibold text-gray-700 border-b">Conversation</div>
                    <div className="max-h-36 overflow-auto p-2 space-y-2">
                      {activeSession.messages.map((message: AgentMessage, index: number) => (
                        <div key={`${message.created_at}-${index}`} className="text-xs">
                          <div className="font-medium text-gray-700">{message.role === 'assistant' ? 'Assistant' : 'You'}</div>
                          <p className="text-gray-600 whitespace-pre-wrap">{message.content}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {agentAnswer && (
                  <div className="rounded border border-gray-200 bg-gray-50 p-2">
                    <div className="text-xs font-semibold text-gray-700 mb-1">Assistant</div>
                    <p className="text-xs text-gray-700 whitespace-pre-wrap">{agentAnswer}</p>
                  </div>
                )}
                <div className="rounded border border-gray-200 bg-white">
                  <div className="px-2 py-1 text-xs font-semibold text-gray-700 border-b">Agent steps</div>
                  <div className="max-h-44 overflow-auto p-2 space-y-2">
                    {agentSteps.map((step, index) => (
                      <div key={`${step.name}-${index}`} className="text-xs">
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-medium text-gray-700">{index + 1}. {step.name}</span>
                          <span className={step.status === 'ok' ? 'badge-green' : 'text-red-600'}>{step.status}</span>
                        </div>
                        <p className="text-gray-600">{step.detail}</p>
                        {step.data && (
                          <pre className="mt-1 max-h-28 overflow-auto rounded bg-gray-50 p-1 text-[10px] text-gray-600">
                            {JSON.stringify(step.data, null, 2)}
                          </pre>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
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
