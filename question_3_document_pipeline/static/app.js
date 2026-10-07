document.addEventListener('DOMContentLoaded', () => {
  const docGrid = document.getElementById('docGrid');
  const inspectorPlaceholder = document.getElementById('inspectorPlaceholder');
  const inspectorDetails = document.getElementById('inspectorDetails');
  const flaggingTableBody = document.getElementById('flaggingTableBody');

  let documentsData = {};
  let selectedFilename = null;

  // 1. Tab Navigation
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

      btn.classList.add('active');
      const tabId = 'tab-' + btn.getAttribute('data-tab');
      const targetContent = document.getElementById(tabId);
      if (targetContent) targetContent.classList.add('active');
    });
  });

  // 2. Fetch Documents and Build Gallery
  async function loadPipelineData() {
    try {
      const res = await fetch('/api/documents');
      const json = await res.json();
      if (json.success && json.data) {
        documentsData = json.data;
        renderDocumentGrid();
        
        // Select first document automatically
        const firstKey = Object.keys(documentsData)[0];
        if (firstKey) selectDocument(firstKey);
      }
    } catch (e) {
      console.error('Failed to load documents data:', e);
    }
  }

  // 3. Render Document Cards
  function renderDocumentGrid() {
    docGrid.innerHTML = '';
    for (const [filename, doc] of Object.entries(documentsData)) {
      const card = document.createElement('div');
      card.className = 'doc-card';
      card.setAttribute('data-filename', filename);

      const hasFlagged = Object.values(doc.extracted_fields).some(f => f.confidence < 0.85);

      card.innerHTML = `
        <img class="doc-thumb" src="/api/image/${encodeURIComponent(filename)}" alt="${escapeHtml(filename)}" onerror="this.src='data:image/svg+xml;utf8,<svg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'56\\' height=\\'56\\'><rect fill=\\'%231e293b\\' width=\\'56\\' height=\\'56\\'/><text fill=\\'%2394a3b8\\' x=\\'28\\' y=\\'32\\' font-size=\\'10\\' text-anchor=\\'middle\\'>DOC</text></svg>'">
        <div class="doc-info">
          <span class="doc-type-badge">${escapeHtml(doc.document_type)}</span>
          <div class="doc-name">${escapeHtml(filename)}</div>
          <div class="doc-meta-row">
            <span class="badge-tag ${doc.is_handwritten ? 'hw' : 'pr'}">${doc.is_handwritten ? '✍️ Handwritten' : '🖨️ Printed'}</span>
            ${hasFlagged ? '<span class="badge-tag hw">⚠️ Review Required</span>' : '<span class="badge-tag pr">✅ High Confidence</span>'}
          </div>
        </div>
      `;

      card.addEventListener('click', () => selectDocument(filename));
      docGrid.appendChild(card);
    }
  }

  // 4. Select and Inspect Document
  function selectDocument(filename) {
    selectedFilename = filename;
    document.querySelectorAll('.doc-card').forEach(c => {
      c.classList.toggle('active', c.getAttribute('data-filename') === filename);
    });

    const doc = documentsData[filename];
    if (!doc) return;

    inspectorPlaceholder.style.display = 'none';
    inspectorDetails.style.display = 'flex';

    let fieldsRows = '';
    for (const [fieldName, fieldInfo] of Object.entries(doc.extracted_fields)) {
      const conf = fieldInfo.confidence;
      const isHigh = conf >= 0.85;

      fieldsRows += `
        <tr>
          <td><strong>${escapeHtml(fieldName)}</strong></td>
          <td><code>${escapeHtml(String(fieldInfo.value))}</code></td>
          <td>
            <span class="conf-pill ${isHigh ? 'high' : 'flagged'}">
              ${(conf * 100).toFixed(0)}% (${conf.toFixed(2)})
            </span>
          </td>
          <td><small style="color: var(--text-dim);">${escapeHtml(fieldInfo.method)}</small></td>
          <td>
            ${isHigh 
              ? '<span style="color: var(--accent-emerald); font-weight:600; font-size:0.75rem;">✅ Accepted</span>' 
              : '<span style="color: var(--accent-amber); font-weight:600; font-size:0.75rem;">⚠️ Flagged for HITL</span>'}
          </td>
        </tr>
      `;
    }

    inspectorDetails.innerHTML = `
      <div class="inspector-header">
        <div>
          <h2>${escapeHtml(doc.document_type)}</h2>
          <span style="font-size: 0.78rem; color: var(--text-dim);">${escapeHtml(filename)}</span>
        </div>
        <div>
          <span class="badge-tag ${doc.is_handwritten ? 'hw' : 'pr'}" style="font-size:0.75rem; padding: 4px 10px;">
            Classification Conf: ${(doc.classification_confidence * 100).toFixed(0)}%
          </span>
        </div>
      </div>

      <div class="inspector-image-wrap">
        <img class="inspector-img" src="/api/image/${encodeURIComponent(filename)}" alt="${escapeHtml(filename)}">
      </div>

      <div class="table-responsive">
        <table class="field-table">
          <thead>
            <tr>
              <th>Required Target Field</th>
              <th>Extracted Value</th>
              <th>Field Confidence</th>
              <th>Extraction Pipeline Method</th>
              <th>Validation Status</th>
            </tr>
          </thead>
          <tbody>
            ${fieldsRows}
          </tbody>
        </table>
      </div>
    `;
  }

  // 5. Fetch and Render Flagging Report Queue
  async function loadFlaggingReport() {
    try {
      const res = await fetch('/api/flagging-report');
      const json = await res.json();
      if (json.success && json.report) {
        const flagged = json.report.flagged_fields || [];
        flaggingTableBody.innerHTML = flagged.map(f => `
          <tr>
            <td><code>${escapeHtml(f.document_filename)}</code></td>
            <td><span class="doc-type-badge">${escapeHtml(f.document_type)}</span></td>
            <td><strong>${escapeHtml(f.field_name)}</strong></td>
            <td><code>${escapeHtml(String(f.extracted_value))}</code></td>
            <td>
              <span class="conf-pill flagged">
                ${(f.confidence_score * 100).toFixed(0)}% (${f.confidence_score.toFixed(2)})
              </span>
            </td>
            <td><small style="color: #fed7aa;">${escapeHtml(f.flagging_reason)}</small></td>
            <td>
              <button class="btn btn-secondary btn-sm" onclick="alert('Field \\'${f.field_name}\\' validated and marked as Verified by Human Reviewer.')">
                ✓ Approve
              </button>
            </td>
          </tr>
        `).join('');
      }
    } catch (e) {
      console.error('Failed to load flagging report:', e);
    }
  }

  function escapeHtml(text) {
    if (typeof text !== 'string') return text;
    return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  loadPipelineData();
  loadFlaggingReport();
});
