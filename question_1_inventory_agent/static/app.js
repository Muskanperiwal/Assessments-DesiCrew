// Inventory Intelligence Agent Frontend Controller
document.addEventListener('DOMContentLoaded', () => {
  const chatMessages = document.getElementById('chatMessages');
  const chatForm = document.getElementById('chatForm');
  const chatInput = document.getElementById('chatInput');
  const btnSend = document.getElementById('btnSend');
  const btnClearChat = document.getElementById('btnClearChat');
  
  // Sidebar elements
  const datasetName = document.getElementById('datasetName');
  const metricSkus = document.getElementById('metricSkus');
  const metricValuation = document.getElementById('metricValuation');
  const btnPreviewData = document.getElementById('btnPreviewData');
  const fileUploadInput = document.getElementById('fileUploadInput');
  const btnResetDefault = document.getElementById('btnResetDefault');
  
  // Modals
  const previewModal = document.getElementById('previewModal');
  const btnClosePreview = document.getElementById('btnClosePreview');
  const previewTableContainer = document.getElementById('previewTableContainer');

  const codeModal = document.getElementById('codeModal');
  const btnCustomCodeModal = document.getElementById('btnCustomCodeModal');
  const btnCloseCodeModal = document.getElementById('btnCloseCodeModal');
  const playgroundCode = document.getElementById('playgroundCode');
  const btnRunPlayground = document.getElementById('btnRunPlayground');
  const playgroundOutput = document.getElementById('playgroundOutput');
  const playgroundStdout = document.getElementById('playgroundStdout');
  const playgroundTableContainer = document.getElementById('playgroundTableContainer');

  let activeDataset = null;

  // 1. Fetch Initial Dataset Information
  async function loadDatasetInfo() {
    try {
      const res = await fetch('/api/dataset-info');
      const json = await res.json();
      if (json.success && json.data) {
        activeDataset = json.data;
        datasetName.textContent = activeDataset.filename || 'Inventory-Records-Sample-Data.xlsx';
        metricSkus.textContent = activeDataset.total_products || '46';
        
        // Find total valuation
        const numSum = activeDataset.numeric_summary;
        let totalVal = 0;
        for (const [col, stats] of Object.entries(numSum)) {
          if (col.toLowerCase().includes('total') && col.toLowerCase().includes('cost')) {
            totalVal = stats.sum;
            break;
          }
        }
        metricValuation.textContent = totalVal ? `$${(totalVal / 1000).toFixed(1)}k` : '$359.8k';
      }
    } catch (err) {
      console.error('Failed to load dataset metadata:', err);
    }
  }

  // 2. Chat Form Submission
  chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const query = chatInput.value.trim();
    if (!query) return;

    // Append user message
    appendUserMessage(query);
    chatInput.value = '';
    chatInput.style.height = 'auto';

    // Show typing indicator
    const typingIndicator = showTypingIndicator();

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: query })
      });
      const data = await res.json();
      typingIndicator.remove();

      if (data.success && data.result) {
        appendAssistantMessage(data.result);
      } else {
        appendErrorMessage(data.error || 'An error occurred while analyzing the data.');
      }
    } catch (err) {
      typingIndicator.remove();
      appendErrorMessage('Failed to connect to the agent backend: ' + err.message);
    }
  });

  // Auto-resize chat textarea
  chatInput.addEventListener('input', () => {
    chatInput.style.height = 'auto';
    chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
  });

  chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      chatForm.dispatchEvent(new Event('submit'));
    }
  });

  // Prompt Chips
  document.querySelectorAll('.prompt-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const prompt = chip.getAttribute('data-prompt');
      chatInput.value = prompt;
      chatForm.dispatchEvent(new Event('submit'));
    });
  });

  // Append User Message Bubble
  function appendUserMessage(text) {
    const wrapper = document.createElement('div');
    wrapper.className = 'message-wrapper user-wrapper';
    wrapper.innerHTML = `
      <div class="user-avatar">👤</div>
      <div class="message-bubble user-bubble">${escapeHtml(text)}</div>
    `;
    chatMessages.appendChild(wrapper);
    scrollToBottom();
  }

  // Show Typing Indicator
  function showTypingIndicator() {
    const typingEl = document.createElement('div');
    typingEl.className = 'typing-indicator';
    typingEl.innerHTML = `
      <div class="typing-dot"></div>
      <div class="typing-dot"></div>
      <div class="typing-dot"></div>
    `;
    chatMessages.appendChild(typingEl);
    scrollToBottom();
    return typingEl;
  }

  // Append Full Assistant Response with Code, Search, Table, and Summary
  function appendAssistantMessage(agentData) {
    const wrapper = document.createElement('div');
    wrapper.className = 'message-wrapper assistant-wrapper';

    let contentHtml = '';

    // 1. Search Tool Card (if triggered)
    if (agentData.search_lookup && agentData.search_lookup.definition) {
      const s = agentData.search_lookup;
      contentHtml += `
        <div class="response-section">
          <div class="section-label">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
            Search Tool Knowledge Lookup (${escapeHtml(s.source)})
          </div>
          <div class="search-card">
            <span class="search-badge">Definition Retrieved</span>
            <div class="search-term">${escapeHtml(s.term || s.query)}</div>
            <div class="search-def">${escapeHtml(s.definition)}</div>
            ${s.formula && s.formula !== 'N/A' ? `<div class="search-meta">📐 Formula: ${escapeHtml(s.formula)}</div>` : ''}
            ${s.business_impact && s.business_impact !== 'N/A' ? `<div class="search-meta">💼 Impact: ${escapeHtml(s.business_impact)}</div>` : ''}
          </div>
        </div>
      `;
    }

    // 2. Generated Python Code Card
    if (agentData.code_generated) {
      contentHtml += `
        <div class="response-section">
          <div class="section-label">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 18 22 12 16 6"></polyline><polyline points="8 6 2 12 8 18"></polyline></svg>
            Automated Python Code Execution
          </div>
          <div class="code-card">
            <div class="code-header">
              <span>Python 3.13 / Pandas</span>
              <span>df Context</span>
            </div>
            <div class="code-block">${escapeHtml(agentData.code_generated)}</div>
          </div>
        </div>
      `;
    }

    // 3. Render Data Table (if execution returned dataframe)
    if (agentData.code_execution && agentData.code_execution.table_data) {
      const t = agentData.code_execution.table_data;
      contentHtml += `
        <div class="response-section">
          <div class="section-label">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 3h18v18H3zM3 9h18M3 15h18M9 3v18M15 3v18"></path></svg>
            Query Execution Output Table (${t.rows.length} rows)
          </div>
          <div class="table-responsive">
            <table class="data-table">
              <thead>
                <tr>${t.columns.map(c => `<th>${escapeHtml(c)}</th>`).join('')}</tr>
              </thead>
              <tbody>
                ${t.rows.map(row => `
                  <tr>${t.columns.map(c => `<td>${escapeHtml(String(row[c] !== undefined ? row[c] : ''))}</td>`).join('')}</tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        </div>
      `;
    }

    // 4. Plain English Executive Summary
    if (agentData.plain_english_summary) {
      const formattedSummary = formatMarkdown(agentData.plain_english_summary);
      contentHtml += `
        <div class="response-section">
          <div class="section-label">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line></svg>
            Executive Summary & Findings
          </div>
          <div class="summary-box">
            ${formattedSummary}
          </div>
        </div>
      `;
    }

    wrapper.innerHTML = `
      <div class="agent-avatar">🤖</div>
      <div class="message-bubble assistant-bubble">${contentHtml}</div>
    `;

    chatMessages.appendChild(wrapper);
    scrollToBottom();
  }

  // Error Message Bubble
  function appendErrorMessage(errText) {
    const wrapper = document.createElement('div');
    wrapper.className = 'message-wrapper assistant-wrapper';
    wrapper.innerHTML = `
      <div class="agent-avatar" style="background: var(--accent-rose);">⚠️</div>
      <div class="message-bubble assistant-bubble">
        <p style="color: var(--accent-rose); font-weight: 600;">Execution Notice:</p>
        <p>${escapeHtml(errText)}</p>
      </div>
    `;
    chatMessages.appendChild(wrapper);
    scrollToBottom();
  }

  // Clear Chat
  btnClearChat.addEventListener('click', () => {
    chatMessages.innerHTML = '';
    loadDatasetInfo();
  });

  // Preview Dataset Modal
  btnPreviewData.addEventListener('click', () => {
    if (!activeDataset || !activeDataset.data_preview) return;
    const preview = activeDataset.data_preview;
    const cols = activeDataset.columns;

    let html = `
      <table class="data-table">
        <thead>
          <tr>${cols.map(c => `<th>${escapeHtml(c)}</th>`).join('')}</tr>
        </thead>
        <tbody>
          ${preview.map(row => `
            <tr>${cols.map(c => `<td>${escapeHtml(String(row[c] !== undefined ? row[c] : ''))}</td>`).join('')}</tr>
          `).join('')}
        </tbody>
      </table>
    `;
    previewTableContainer.innerHTML = html;
    previewModal.style.display = 'flex';
  });

  btnClosePreview.addEventListener('click', () => {
    previewModal.style.display = 'none';
  });

  // File Upload Handler
  fileUploadInput.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    const typing = showTypingIndicator();
    try {
      const res = await fetch('/api/upload', {
        method: 'POST',
        body: formData
      });
      const data = await res.json();
      typing.remove();

      if (data.success) {
        await loadDatasetInfo();
        appendAssistantMessage({
          plain_english_summary: `### 📁 Custom Dataset Successfully Loaded!\n- **File:** \`${file.name}\`\n- **Records:** ${data.data.total_products} rows loaded.\n- The agent is now ready to query this new dataset!`
        });
      } else {
        appendErrorMessage('Upload failed: ' + data.error);
      }
    } catch (err) {
      typing.remove();
      appendErrorMessage('Upload failed: ' + err.message);
    }
  });

  // Reset to Default Sample
  btnResetDefault.addEventListener('click', async () => {
    try {
      const res = await fetch('/api/reset', { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        await loadDatasetInfo();
        appendAssistantMessage({
          plain_english_summary: `### 🔄 Reset Completed\nSwitched back to default sample inventory dataset (\`Inventory-Records-Sample-Data.xlsx\`).`
        });
      }
    } catch (err) {
      alert('Reset failed: ' + err.message);
    }
  });

  // Python Playground Modal
  btnCustomCodeModal.addEventListener('click', () => {
    codeModal.style.display = 'flex';
  });

  btnCloseCodeModal.addEventListener('click', () => {
    codeModal.style.display = 'none';
  });

  btnRunPlayground.addEventListener('click', async () => {
    const code = playgroundCode.value.trim();
    if (!code) return;

    btnRunPlayground.disabled = true;
    btnRunPlayground.textContent = 'Running...';
    try {
      const res = await fetch('/api/execute-code', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code })
      });
      const data = await res.json();
      btnRunPlayground.disabled = false;
      btnRunPlayground.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg> Execute Script';

      playgroundOutput.style.display = 'block';
      if (data.success && data.execution) {
        const ex = data.execution;
        playgroundStdout.textContent = ex.stdout || ex.result || (ex.success ? 'Success' : ex.error);

        if (ex.table_data) {
          const t = ex.table_data;
          playgroundTableContainer.innerHTML = `
            <table class="data-table" style="margin-top: 10px;">
              <thead><tr>${t.columns.map(c => `<th>${escapeHtml(c)}</th>`).join('')}</tr></thead>
              <tbody>${t.rows.map(row => `<tr>${t.columns.map(c => `<td>${escapeHtml(String(row[c] !== undefined ? row[c] : ''))}</td>`).join('')}</tr>`).join('')}</tbody>
            </table>
          `;
        } else {
          playgroundTableContainer.innerHTML = '';
        }
      }
    } catch (err) {
      btnRunPlayground.disabled = false;
      alert('Execution failed: ' + err.message);
    }
  });

  // Utilities
  function scrollToBottom() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function escapeHtml(text) {
    if (typeof text !== 'string') return text;
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function formatMarkdown(md) {
    if (!md) return '';
    let html = escapeHtml(md);
    
    // Convert headers
    html = html.replace(/^### (.*$)/gim, '<h4>$1</h4>');
    html = html.replace(/^## (.*$)/gim, '<h3>$1</h3>');
    html = html.replace(/^# (.*$)/gim, '<h2>$1</h2>');
    
    // Bold & italic
    html = html.replace(/\*\*(.*?)\*\*/gim, '<strong>$1</strong>');
    html = html.replace(/\*(.*?)\*/gim, '<em>$1</em>');
    
    // Inline code
    html = html.replace(/`(.*?)`/gim, '<code>$1</code>');
    
    // Blockquote
    html = html.replace(/^&gt; (.*$)/gim, '<div class="quote-box">$1</div>');
    
    // Lists
    html = html.replace(/^\- (.*$)/gim, '<li>$1</li>');
    html = html.replace(/\n\n/g, '<br>');
    return html;
  }

  // Load dataset metadata on start
  loadDatasetInfo();
});
