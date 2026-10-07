document.addEventListener('DOMContentLoaded', () => {
  const chatMessages = document.getElementById('chatMessages');
  const chatForm = document.getElementById('chatForm');
  const chatInput = document.getElementById('chatInput');
  const btnSend = document.getElementById('btnSend');
  const btnRun10TurnDemo = document.getElementById('btnRun10TurnDemo');
  const btnResetSession = document.getElementById('btnResetSession');

  // HUD elements
  const hudTurns = document.getElementById('hudTurns');
  const hudSwitches = document.getElementById('hudSwitches');
  const hudFacts = document.getElementById('hudFacts');
  const hudTopicsCount = document.getElementById('hudTopicsCount');
  const hudActiveTopic = document.getElementById('hudActiveTopic');
  const docsList = document.getElementById('docsList');

  // 1. Fetch and Display Knowledge Base Documents
  async function loadDocuments() {
    try {
      const res = await fetch('/api/documents');
      const data = await res.json();
      if (data.success && data.documents) {
        docsList.innerHTML = data.documents.map(d => `
          <div class="doc-item">
            <div class="doc-title-row">
              <span>📄 ${escapeHtml(d.filename)}</span>
              <span class="doc-badge">${d.sections_count} sections</span>
            </div>
          </div>
        `).join('');
      }
    } catch (e) {
      console.error('Failed to load documents:', e);
    }
  }

  // 2. Fetch and Update Session Memory HUD
  async function updateSessionHUD() {
    try {
      const res = await fetch('/api/session-state');
      const data = await res.json();
      if (data.success && data.state) {
        const s = data.state;
        hudTurns.textContent = s.total_turns || 0;
        hudSwitches.textContent = s.topic_switches_count || 0;
        hudFacts.textContent = s.total_facts_delivered || 0;
        hudTopicsCount.textContent = (s.topic_history || []).length;
        hudActiveTopic.textContent = s.active_topic || 'None (Session Not Started)';
      }
    } catch (e) {
      console.error('Failed to update session HUD:', e);
    }
  }

  // 3. User Message Submission
  chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const query = chatInput.value.trim();
    if (!query) return;

    appendUserMessage(query);
    chatInput.value = '';
    chatInput.style.height = 'auto';

    const typingEl = showTypingIndicator();

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: query })
      });
      const data = await res.json();
      typingEl.remove();

      if (data.success && data.result) {
        appendAssistantMessage(data.result);
        await updateSessionHUD();
      } else {
        appendErrorMessage(data.error || 'Failed to process turn.');
      }
    } catch (err) {
      typingEl.remove();
      appendErrorMessage('Connection error: ' + err.message);
    }
  });

  // 4. Run 10-Turn Scripted Demonstration
  btnRun10TurnDemo.addEventListener('click', async () => {
    btnRun10TurnDemo.disabled = true;
    btnRun10TurnDemo.innerHTML = '⏳ Executing 10 Turns...';

    // Reset chat
    chatMessages.innerHTML = '';
    const startMsg = document.createElement('div');
    startMsg.className = 'message-wrapper assistant-wrapper';
    startMsg.innerHTML = `
      <div class="agent-avatar">🚀</div>
      <div class="message-bubble assistant-bubble">
        <strong>Starting Automated 10-Turn Benchmark Demonstration...</strong>
        <p>Testing memory retention, anti-repetition, topic transitions, and document citations turn-by-turn.</p>
      </div>
    `;
    chatMessages.appendChild(startMsg);

    try {
      const res = await fetch('/api/run-10-turn-demo', { method: 'POST' });
      const data = await res.json();

      if (data.success && data.turns) {
        chatMessages.innerHTML = '';
        for (let i = 0; i < data.turns.length; i++) {
          const t = data.turns[i];
          appendUserMessage(t.user_query);
          appendAssistantMessage(t);
          await new Promise(r => setTimeout(r, 150));
        }
        await updateSessionHUD();
      } else {
        appendErrorMessage('Benchmark failed: ' + data.error);
      }
    } catch (err) {
      appendErrorMessage('Failed to execute demonstration: ' + err.message);
    } finally {
      btnRun10TurnDemo.disabled = false;
      btnRun10TurnDemo.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg> Run 10-Turn Demonstration';
    }
  });

  // 5. Reset Session Memory
  btnResetSession.addEventListener('click', async () => {
    try {
      const res = await fetch('/api/reset', { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        chatMessages.innerHTML = `
          <div class="message-wrapper assistant-wrapper">
            <div class="agent-avatar">🔄</div>
            <div class="message-bubble assistant-bubble">
              <p>Session memory has been reset to an initial empty state.</p>
            </div>
          </div>
        `;
        await updateSessionHUD();
      }
    } catch (e) {
      alert('Reset failed: ' + e.message);
    }
  });

  // Quick Prompt Chips
  document.querySelectorAll('.prompt-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      chatInput.value = btn.getAttribute('data-query');
      chatForm.dispatchEvent(new Event('submit'));
    });
  });

  // Message Renderers
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

  function appendAssistantMessage(turnData) {
    const wrapper = document.createElement('div');
    wrapper.className = 'message-wrapper assistant-wrapper';

    let badgesHtml = '';
    if (turnData.is_topic_switch) {
      badgesHtml += `
        <div class="topic-switch-pill">
          🔀 Topic Switch: ${escapeHtml(turnData.topic)}
        </div>
      `;
    }
    if (turnData.already_delivered_facts && turnData.already_delivered_facts.length > 0) {
      badgesHtml += `
        <div class="anti-repetition-pill">
          🛡️ Anti-Repetition Filtered (${turnData.already_delivered_facts.length} facts preserved)
        </div>
      `;
    }

    const citationHtml = `
      <div class="citation-card">
        <span>📖 Section Citation:</span>
        <code>[${escapeHtml(turnData.citation)}]</code>
      </div>
    `;

    wrapper.innerHTML = `
      <div class="agent-avatar">🤖</div>
      <div class="message-bubble assistant-bubble">
        ${badgesHtml}
        <div class="reply-text">${formatMarkdown(turnData.reply)}</div>
        ${citationHtml}
      </div>
    `;

    chatMessages.appendChild(wrapper);
    scrollToBottom();
  }

  function appendErrorMessage(errText) {
    const wrapper = document.createElement('div');
    wrapper.className = 'message-wrapper assistant-wrapper';
    wrapper.innerHTML = `
      <div class="agent-avatar" style="background: var(--accent-rose);">⚠️</div>
      <div class="message-bubble assistant-bubble">
        <p style="color: var(--accent-rose);">${escapeHtml(errText)}</p>
      </div>
    `;
    chatMessages.appendChild(wrapper);
    scrollToBottom();
  }

  function showTypingIndicator() {
    const el = document.createElement('div');
    el.className = 'message-wrapper assistant-wrapper';
    el.innerHTML = `
      <div class="agent-avatar">🤖</div>
      <div class="message-bubble assistant-bubble" style="padding: 10px 14px;">
        <span style="color: var(--text-dim); font-size: 0.8rem;">Retrieving document section & evaluating context...</span>
      </div>
    `;
    chatMessages.appendChild(el);
    scrollToBottom();
    return el;
  }

  function scrollToBottom() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function escapeHtml(text) {
    if (typeof text !== 'string') return text;
    return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function formatMarkdown(md) {
    if (!md) return '';
    let html = escapeHtml(md);
    html = html.replace(/\*\*(.*?)\*\*/gim, '<strong>$1</strong>');
    html = html.replace(/\*(.*?)\*/gim, '<em>$1</em>');
    html = html.replace(/`(.*?)`/gim, '<code>$1</code>');
    html = html.replace(/^&gt; (.*$)/gim, '<blockquote style="border-left: 3px solid var(--accent-emerald); padding-left: 8px; color: #a7f3d0; margin: 4px 0;">$1</blockquote>');
    html = html.replace(/^\- (.*$)/gim, '<li style="margin-left: 16px;">$1</li>');
    html = html.replace(/\n\n/g, '<br><br>');
    return html;
  }

  loadDocuments();
  updateSessionHUD();
});
