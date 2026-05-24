'use strict';

// ── State ────────────────────────────────────────────────────────────────
let cy = null;
let activeEdge = null;  // Cytoscape edge element currently shown in sidebar

// ── Bootstrap modal handles (created lazily) ─────────────────────────────
let modalAddEdge = null;
let modalAddDs   = null;

// ── Example QDVM query (mirrors examples/customer_summary.qdvm) ───────────
const EXAMPLE_QUERY = `define X on custID:
  compute A on Age transformedby 'aggregate:any'
  compute G on Gender transformedby 'aggregate:any'
  compute N on Comment transformedby 'map:python,,len($N$);aggregate:sum'
  output A,G,N
  where True`;

// ═══════════════════════════════════════════════════════════════════════════
// Initialisation
// ═══════════════════════════════════════════════════════════════════════════
document.addEventListener('DOMContentLoaded', () => {
  // Pre-fill query editor
  document.getElementById('query-text').value = EXAMPLE_QUERY;

  // Lazy-create Bootstrap modals
  modalAddEdge = new bootstrap.Modal(document.getElementById('modal-add-edge'));
  modalAddDs   = new bootstrap.Modal(document.getElementById('modal-add-ds'));

  // Wire up buttons
  document.getElementById('btn-add-edge').addEventListener('click', openAddEdgeModal);
  document.getElementById('btn-del-edge').addEventListener('click', deleteActiveEdge);
  document.getElementById('btn-refresh-dvm').addEventListener('click', refreshDVM);
  document.getElementById('btn-save-edge').addEventListener('click', saveEdge);
  document.getElementById('btn-run-json').addEventListener('click', () => runQuery('json'));
  document.getElementById('btn-run-csv').addEventListener('click',  () => runQuery('csv'));
  document.getElementById('btn-load-example').addEventListener('click', loadExample);
  document.getElementById('btn-add-ds').addEventListener('click', openAddDsModal);
  document.getElementById('btn-save-ds').addEventListener('click', saveDatasource);
  document.getElementById('ds-type').addEventListener('change', renderDsFields);

  // Resize Cytoscape when DVM tab becomes visible
  document.getElementById('tab-dvm').addEventListener('shown.bs.tab', () => {
    if (cy) cy.resize().fit(undefined, 30);
  });

  // Initial data loads
  loadDVM();
  loadDatasources();
});

// ═══════════════════════════════════════════════════════════════════════════
// DVM Canvas
// ═══════════════════════════════════════════════════════════════════════════
async function loadDVM() {
  try {
    const res = await fetch('/dvm');
    if (!res.ok) throw new Error(await res.text());
    renderDVM(await res.json());
  } catch (err) {
    console.error('DVM load failed:', err);
  }
}

function renderDVM(data) {
  const elements = [];

  // Nodes
  for (const node of data.nodes) {
    elements.push({ data: { id: node.name, label: node.name, description: node.description } });
  }

  // Edges — use a unique id so parallel edges (same head/tail) all appear
  data.edges.forEach((e, idx) => {
    elements.push({
      data: {
        id: `${e.head}--${e.tail}--${idx}`,
        source: e.head,
        target: e.tail,
        label: e.datasource,
        // store all DVM fields; prefix with dvm_ to avoid Cytoscape conflicts
        dvmHead: e.head,
        dvmTail: e.tail,
        dvmDatasource: e.datasource,
        dvmQuery: e.query,
        dvmKey: e.key,
        dvmValue: e.value,
        dvmSelected: e.selected,   // true/false — controls edge colour
        dvmDescription: e.description,
        dvmHeadDesc: e.head_description,
        dvmTailDesc: e.tail_description,
      },
    });
  });

  if (cy) cy.destroy();

  cy = cytoscape({
    container: document.getElementById('cy'),
    elements,
    style: [
      {
        selector: 'node',
        style: {
          'background-color': '#6ea8fe',
          'border-color': '#3d8bfd',
          'border-width': 2,
          'label': 'data(label)',
          'color': '#1a1a2e',
          'text-valign': 'center',
          'text-halign': 'center',
          'font-size': '11px',
          'font-weight': '600',
          'width': 72,
          'height': 72,
        },
      },
      {
        selector: 'node:selected',
        style: { 'border-color': '#dc3545', 'border-width': 3 },
      },
      {
        // unselected DVM edges
        selector: 'edge[!dvmSelected]',
        style: {
          'width': 2,
          'line-color': '#adb5bd',
          'target-arrow-color': '#adb5bd',
          'target-arrow-shape': 'triangle',
          'curve-style': 'bezier',
          'label': 'data(label)',
          'font-size': '9px',
          'color': '#6c757d',
          'text-background-color': '#fff',
          'text-background-opacity': 0.8,
          'text-background-padding': '2px',
        },
      },
      {
        // selected DVM edges (green)
        selector: 'edge[?dvmSelected]',
        style: {
          'width': 3,
          'line-color': '#198754',
          'target-arrow-color': '#198754',
          'target-arrow-shape': 'triangle',
          'curve-style': 'bezier',
          'label': 'data(label)',
          'font-size': '9px',
          'color': '#146c43',
          'text-background-color': '#fff',
          'text-background-opacity': 0.8,
          'text-background-padding': '2px',
        },
      },
      {
        selector: 'edge:selected',
        style: { 'line-color': '#fd7e14', 'target-arrow-color': '#fd7e14', 'width': 4 },
      },
    ],
    layout: { name: 'cose', padding: 40, animate: false, randomize: false },
  });

  // Tap on an edge → show sidebar details
  cy.on('tap', 'edge', evt => {
    activeEdge = evt.target;
    showEdgeSidebar(evt.target.data());
  });

  // Tap on background → hide sidebar
  cy.on('tap', evt => {
    if (evt.target === cy) {
      activeEdge = null;
      document.getElementById('card-edge-info').classList.add('d-none');
    }
  });
}

function showEdgeSidebar(d) {
  const card = document.getElementById('card-edge-info');
  const body = document.getElementById('edge-info-body');
  card.classList.remove('d-none');

  const sel = d.dvmSelected
    ? '<span class="badge bg-success">yes</span>'
    : '<span class="badge bg-secondary">no</span>';

  body.innerHTML = `
    <table class="table table-sm mb-2">
      <tr><th>Head</th><td>${d.dvmHead}</td></tr>
      <tr><th>Tail</th><td>${d.dvmTail}</td></tr>
      <tr><th>Datasource</th><td>${d.dvmDatasource || '—'}</td></tr>
      <tr><th>Key col</th><td>${d.dvmKey || '—'}</td></tr>
      <tr><th>Value col</th><td>${d.dvmValue || '—'}</td></tr>
      <tr><th>SQL query</th><td class="text-break">${d.dvmQuery || '—'}</td></tr>
      <tr><th>Selected</th><td>${sel}</td></tr>
    </table>
    <button class="btn btn-sm w-100 ${d.dvmSelected ? 'btn-outline-secondary' : 'btn-outline-success'}"
            onclick="toggleEdgeSelected('${d.dvmHead}', '${d.dvmTail}', ${!d.dvmSelected})">
      ${d.dvmSelected ? 'Deselect edge' : 'Select edge'}
    </button>
  `;
}

async function toggleEdgeSelected(head, tail, newValue) {
  try {
    const res = await fetch('/dvm/edge', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ head, tail, selected: newValue }),
    });
    if (!res.ok) throw new Error(await res.text());
    await loadDVM();
    // Re-select the same edge in the refreshed graph so sidebar stays open
    requestAnimationFrame(() => {
      const el = cy.edges().filter(e => e.data('dvmHead') === head && e.data('dvmTail') === tail).first();
      if (el.length) showEdgeSidebar(el.data());
    });
  } catch (err) {
    alert('Failed to update edge:\n' + err);
  }
}

async function deleteActiveEdge() {
  if (!activeEdge) {
    alert('Click an edge in the graph to select it first.');
    return;
  }
  const { dvmHead: head, dvmTail: tail } = activeEdge.data();
  if (!confirm(`Delete edge ${head} → ${tail}?`)) return;
  try {
    const res = await fetch(`/dvm/edge?head=${encodeURIComponent(head)}&tail=${encodeURIComponent(tail)}`, {
      method: 'DELETE',
    });
    if (!res.ok) throw new Error(await res.text());
    activeEdge = null;
    document.getElementById('card-edge-info').classList.add('d-none');
    await loadDVM();
  } catch (err) {
    alert('Failed to delete edge:\n' + err);
  }
}

async function refreshDVM() {
  activeEdge = null;
  document.getElementById('card-edge-info').classList.add('d-none');
  await loadDVM();
}

function openAddEdgeModal() {
  // Clear previous values
  ['edge-head', 'edge-tail', 'edge-datasource', 'edge-key', 'edge-value', 'edge-query'].forEach(id => {
    document.getElementById(id).value = '';
  });
  document.getElementById('edge-selected-check').checked = false;
  modalAddEdge.show();
}

async function saveEdge() {
  const head       = document.getElementById('edge-head').value.trim();
  const tail       = document.getElementById('edge-tail').value.trim();
  const datasource = document.getElementById('edge-datasource').value.trim();
  const key        = document.getElementById('edge-key').value.trim();
  const value      = document.getElementById('edge-value').value.trim();
  const query      = document.getElementById('edge-query').value.trim();
  const selected   = document.getElementById('edge-selected-check').checked;

  if (!head || !tail || !datasource) {
    alert('Head, tail, and datasource are required.');
    return;
  }
  try {
    const res = await fetch('/dvm/edge', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ head, tail, datasource, key, value, query, selected }),
    });
    if (!res.ok) throw new Error(await res.text());
    modalAddEdge.hide();
    await loadDVM();
  } catch (err) {
    alert('Failed to add edge:\n' + err);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// Query Builder
// ═══════════════════════════════════════════════════════════════════════════
function loadExample(e) {
  e.preventDefault();
  document.getElementById('query-text').value = EXAMPLE_QUERY;
}

async function runQuery(format) {
  const queryText = document.getElementById('query-text').value.trim();
  const resultsEl = document.getElementById('query-results');
  const badgeEl   = document.getElementById('badge-status');
  const errorBar  = document.getElementById('bar-error');
  const errorText = document.getElementById('text-error');

  errorBar.classList.add('d-none');
  badgeEl.classList.remove('d-none');
  badgeEl.textContent = 'Running…';
  resultsEl.textContent = '';

  try {
    const endpoint = format === 'csv' ? '/eval-csv' : '/eval';
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain' },
      body: queryText,
    });

    if (!res.ok) {
      const msg = await res.text();
      errorText.textContent = msg;
      errorBar.classList.remove('d-none');
      badgeEl.classList.add('d-none');
      return;
    }

    if (format === 'csv') {
      resultsEl.textContent = await res.text();
      badgeEl.textContent = 'CSV';
      badgeEl.className = 'badge text-bg-secondary';
    } else {
      const data = await res.json();
      resultsEl.textContent = JSON.stringify(data, null, 2);
      const count = Array.isArray(data) ? data.length : Object.keys(data).length;
      badgeEl.textContent = `${count} record${count !== 1 ? 's' : ''}`;
      badgeEl.className = 'badge text-bg-success';
    }
  } catch (err) {
    errorText.textContent = err.toString();
    errorBar.classList.remove('d-none');
    badgeEl.classList.add('d-none');
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// Datasources
// ═══════════════════════════════════════════════════════════════════════════
async function loadDatasources() {
  try {
    const res = await fetch('/datasources');
    if (!res.ok) throw new Error(await res.text());
    renderDatasources(await res.json());
  } catch (err) {
    console.error('Datasources load failed:', err);
  }
}

function renderDatasources(sources) {
  const container = document.getElementById('ds-table');
  if (!sources.length) {
    container.innerHTML = '<p class="text-muted small">No datasources defined.</p>';
    return;
  }

  const rows = sources.map(s => {
    const opts = Object.entries(s)
      .filter(([k]) => k !== 'name' && k !== 'type')
      .map(([k, v]) => `<span class="badge text-bg-light border me-1">${k}: ${esc(v)}</span>`)
      .join('');
    return `<tr>
      <td class="fw-semibold">${esc(s.name)}</td>
      <td><span class="badge text-bg-secondary">${esc(s.type)}</span></td>
      <td>${opts}</td>
      <td class="text-end">
        <button class="btn btn-sm btn-outline-danger py-0 px-2"
                onclick="deleteDatasource('${esc(s.name)}')">Delete</button>
      </td>
    </tr>`;
  }).join('');

  container.innerHTML = `
    <table class="table table-sm table-hover align-middle">
      <thead class="table-light">
        <tr><th>Name</th><th>Type</th><th>Options</th><th></th></tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
}

async function deleteDatasource(name) {
  if (!confirm(`Delete datasource "${name}"?`)) return;
  try {
    const res = await fetch(`/datasources/${encodeURIComponent(name)}`, { method: 'DELETE' });
    if (!res.ok) throw new Error(await res.text());
    await loadDatasources();
  } catch (err) {
    alert('Failed to delete datasource:\n' + err);
  }
}

function openAddDsModal() {
  document.getElementById('ds-name').value = '';
  document.getElementById('ds-type').value = 'csv';
  renderDsFields();
  modalAddDs.show();
}

// Render type-specific option fields inside the Add Datasource modal
function renderDsFields() {
  const type = document.getElementById('ds-type').value;
  const target = document.getElementById('ds-dynamic-fields');

  const templates = {
    csv: `
      <div class="row g-2">
        <div class="col-8">
          <label class="form-label small mb-1">Path (directory)</label>
          <input type="text" class="form-control form-control-sm ds-opt" data-key="path" placeholder=".">
        </div>
        <div class="col-12">
          <label class="form-label small mb-1">Filename</label>
          <input type="text" class="form-control form-control-sm ds-opt" data-key="filename" placeholder="data.csv">
        </div>
        <div class="col-4">
          <label class="form-label small mb-1">Delimiter</label>
          <input type="text" class="form-control form-control-sm ds-opt" data-key="delimiter" value=",">
        </div>
        <div class="col-4">
          <label class="form-label small mb-1">Has headings?</label>
          <select class="form-select form-select-sm ds-opt" data-key="headings">
            <option value="yes">Yes</option>
            <option value="no">No</option>
          </select>
        </div>
      </div>`,
    excel: `
      <div class="row g-2">
        <div class="col-8">
          <label class="form-label small mb-1">Path (directory)</label>
          <input type="text" class="form-control form-control-sm ds-opt" data-key="path" placeholder=".">
        </div>
        <div class="col-12">
          <label class="form-label small mb-1">Filename</label>
          <input type="text" class="form-control form-control-sm ds-opt" data-key="filename" placeholder="data.xlsx">
        </div>
        <div class="col-6">
          <label class="form-label small mb-1">Sheet name (optional)</label>
          <input type="text" class="form-control form-control-sm ds-opt" data-key="sheet" placeholder="Sheet1">
        </div>
      </div>`,
    db: `
      <div class="row g-2">
        <div class="col-12">
          <label class="form-label small mb-1">Connection string</label>
          <input type="text" class="form-control form-control-sm ds-opt" data-key="connection"
                 placeholder="sqlite:///path/to/db.sqlite">
          <div class="form-text">SQLite or SQLAlchemy URL</div>
        </div>
      </div>`,
    process: `
      <div class="row g-2">
        <div class="col-12">
          <label class="form-label small mb-1">System command</label>
          <input type="text" class="form-control form-control-sm ds-opt" data-key="system"
                 placeholder="python generate.py">
        </div>
        <div class="col-4">
          <label class="form-label small mb-1">Delimiter</label>
          <input type="text" class="form-control form-control-sm ds-opt" data-key="delimiter" value=",">
        </div>
      </div>`,
  };

  target.innerHTML = templates[type] || '';
}

async function saveDatasource() {
  const name = document.getElementById('ds-name').value.trim();
  const type = document.getElementById('ds-type').value;
  if (!name) { alert('Name is required.'); return; }

  const body = { name, type };
  document.querySelectorAll('.ds-opt').forEach(el => {
    const v = el.value.trim();
    if (v) body[el.dataset.key] = v;
  });

  try {
    const res = await fetch('/datasources', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(await res.text());
    modalAddDs.hide();
    await loadDatasources();
  } catch (err) {
    alert('Failed to add datasource:\n' + err);
  }
}

// ── Utility ──────────────────────────────────────────────────────────────
function esc(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
