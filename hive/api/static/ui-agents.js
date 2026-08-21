/* ═══ AGENTS MODULE ═══ */

function renderTemplateGrid() {
  const cats = ['All', ...new Set(allTemplates.map(t => t.category))];
  $('agentTabs').innerHTML = cats.map(c => `<div class="agTab${c === agentFilter ? ' active' : ''}" onclick="agentFilter='${c}';renderTemplateGrid()">${c}</div>`).join('');
  const filtered = agentFilter === 'All' ? allTemplates : allTemplates.filter(t => t.category === agentFilter);
  const icons = {
    coding_assistant: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>',
    researcher: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>',
    writer: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/></svg>',
    data_analyst: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>',
    sysadmin: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>',
    teacher: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>',
    rag_assistant: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>',
    creative: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>',
    lead_research: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>',
    outreach: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>',
    discovery_summarizer: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>',
    proposal_generator: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>',
    follow_up: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>',
    seo_strategy: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>',
    content_brief: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>',
    blog_writer: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 19l7-7 3 3-7 7-3-3z"/><path d="M18 13l-1.5-7.5L2 2l3.5 14.5L13 18l5-5z"/><path d="M2 2l7.586 7.586"/><circle cx="11" cy="11" r="2"/></svg>',
    social_media: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>',
    paid_ads: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>',
    email_marketing: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>',
    landing_page: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/></svg>',
    creative_brief: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>',
    video_script: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2"/></svg>',
    onboarding: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
    meeting_notes: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>',
    weekly_update: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>',
    client_reporting: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>',
    upsell_retention: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>',
    project_manager: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>',
    resource_planner: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect x="8" y="2" width="8" height="4" rx="1"/><path d="M9 14l2 2 4-4"/></svg>',
    sop_generator: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>',
    knowledge_base: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>',
    competitor_analysis: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><line x1="14.31" y1="8" x2="20.05" y2="17.94"/><line x1="9.69" y1="8" x2="21.17" y2="8"/><line x1="7.38" y1="12" x2="13.12" y2="2.06"/><line x1="9.69" y1="16" x2="3.95" y2="6.06"/><line x1="14.31" y1="16" x2="2.83" y2="16"/><line x1="16.62" y1="12" x2="10.88" y2="21.94"/></svg>',
    customer_insight: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>',
    brand_voice: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>',
    design_prompt: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="13.5" cy="6.5" r=".5"/><circle cx="17.5" cy="10.5" r=".5"/><circle cx="8.5" cy="7.5" r=".5"/><circle cx="6.5" cy="12.5" r=".5"/><path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125a1.64 1.64 0 0 1 1.668-1.668h1.996c3.051 0 5.555-2.503 5.555-5.554C21.965 6.012 17.461 2 12 2z"/></svg>'
  };
  const defaultIcon = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 2v3M8 8v3M16 8v3"/></svg>';
  const useCases = {
    coding_assistant: ['Write & debug code', 'Code reviews', 'Architecture design'],
    researcher: ['Deep research', 'Source verification', 'Summarization'],
    writer: ['Content creation', 'Editing & proofreading', 'Style adaptation'],
    data_analyst: ['Data analysis', 'Visualization', 'Statistical modeling'],
    sysadmin: ['Server management', 'Deployment', 'Monitoring'],
    teacher: ['Lesson planning', 'Q&A', 'Explanation'],
    rag_assistant: ['Document Q&A', 'Knowledge retrieval', 'Context-aware answers'],
    creative: ['Brainstorming', 'Concept development', 'Creative writing'],
    lead_research: ['Lead discovery', 'Qualification', 'Outreach strategy'],
    outreach: ['Email campaigns', 'Personalization', 'Follow-ups'],
    discovery_summarizer: ['Call summaries', 'Key insights', 'Action items'],
    proposal_generator: ['Proposal drafting', 'Pricing', 'Scope definition'],
    follow_up: ['Client follow-ups', 'Nurture sequences', 'Re-engagement'],
    seo_strategy: ['Keyword research', 'Content planning', 'Technical SEO'],
    content_brief: ['Content planning', 'Brief creation', 'Topic research'],
    blog_writer: ['Article writing', 'SEO optimization', 'Editing'],
    social_media: ['Post creation', 'Calendar planning', 'Engagement'],
    paid_ads: ['Ad copy', 'Audience targeting', 'A/B testing'],
    email_marketing: ['Email sequences', 'Subject lines', 'Segmentation'],
    landing_page: ['Copy writing', 'Conversion optimization', 'Layout suggestions'],
    creative_brief: ['Brief creation', 'Direction setting', 'Asset planning'],
    video_script: ['Script writing', 'Storyboard', 'Shot lists'],
    onboarding: ['Client onboarding', 'Documentation', 'Training'],
    meeting_notes: ['Note taking', 'Action items', 'Summaries'],
    weekly_update: ['Status reports', 'Progress tracking', 'Client updates'],
    client_reporting: ['Performance reports', 'Analytics', 'Insights'],
    upsell_retention: ['Opportunity identification', 'Retention strategies', 'Upsell pitches'],
    project_manager: ['Task planning', 'Timeline management', 'Resource allocation'],
    resource_planner: ['Capacity planning', 'Workload balancing', 'Scheduling'],
    sop_generator: ['Process documentation', 'Standardization', 'Training'],
    knowledge_base: ['FAQ creation', 'Documentation', 'Knowledge organization'],
    competitor_analysis: ['Market research', 'Competitive intelligence', 'Strategy'],
    customer_insight: ['Feedback analysis', 'User research', 'Insights'],
    brand_voice: ['Voice guidelines', 'Tone consistency', 'Brand messaging'],
    design_prompt: ['Visual concepts', 'Art direction', 'Style guides']
  };
  
  $('templateGrid').innerHTML = filtered.map(x => {
    const tools = x.tools ? (typeof x.tools === 'string' ? JSON.parse(x.tools || '[]') : x.tools) : [];
    const toolIcons = {
      'web_search': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/></svg>',
      'calculator': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="4" y="2" width="16" height="20" rx="2"/><line x1="8" y1="6" x2="16" y2="6"/></svg>',
      'execute_code': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>'
    };
    const cases = useCases[x.id] || ['General assistance', 'Task automation', 'Quick answers'];
    return `<div class="agCard" onclick="createFromTemplate('${x.id}','${esc(x.name)}')">
      <div class="agCat"><span class="pill pN">${x.category}</span></div>
      <div class="agIc" style="background:var(--bg4);border:1px solid var(--bd2);color:var(--tx)">${icons[x.id] || defaultIcon}</div>
      <div class="agN">${esc(x.name)}</div>
      <div class="agD">${esc(x.description)}</div>
      <div class="agStats">
        <div class="agStat">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
          <span>temp</span>
          <span class="agStatValue">${x.temperature || 0.7}</span>
        </div>
        <div class="agStat">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 2v20M2 12h20"/></svg>
          <span class="agStatValue">${(x.max_tokens || 4096) / 1000}K</span>
          <span>tokens</span>
        </div>
      </div>
      <div style="margin:12px 0">
        <div style="font-size:11px;font-weight:600;color:var(--tx2);margin-bottom:8px;text-transform:uppercase;letter-spacing:0.5px">Use Cases</div>
        ${cases.map(c => `<div style="font-size:11px;color:var(--tx3);padding:4px 0;border-left:2px solid var(--bd2);padding-left:10px;margin-bottom:4px">${c}</div>`).join('')}
      </div>
      ${tools.length ? `<div class="agTools">
        ${tools.slice(0, 4).map(t => `<div class="agTool">${toolIcons[t] || '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/></svg>'}<span>${t.replace(/_/g, ' ')}</span></div>`).join('')}
        ${tools.length > 4 ? `<div class="agTool">+${tools.length-4}</div>` : ''}
      </div>` : ''}
      <div class="agQuickActions">
        <button class="agQuickBtn" onclick="event.stopPropagation();previewTemplate('${x.id}')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
          Preview
        </button>
        <button class="agQuickBtn" onclick="event.stopPropagation();createFromTemplate('${x.id}','${esc(x.name)}')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          Create
        </button>
      </div>
    </div>`;
  }).join('') || '<div style="color:var(--tx3);padding:16px;font-size:13px">No templates in this category</div>';
}

function createAgent() {
  const n = $('naN').value.trim();
  const p = $('naP').value.trim();
  const pr = $('naPr').value;
  const m = $('naM').value;
  if (!n) { toast('Agent name is required','warning'); $('naN').focus(); return; }
  if (n.length < 2) { toast('Agent name must be at least 2 characters','warning'); $('naN').focus(); return; }
  if (n.length > 50) { toast('Agent name must be less than 50 characters','warning'); $('naN').focus(); return; }
  if (!p) { toast('System prompt is required','warning'); $('naP').focus(); return; }
  if (p.length < 10) { toast('System prompt must be at least 10 characters','warning'); $('naP').focus(); return; }
  
  api('/api/agents', {
    method: 'POST',
    body: JSON.stringify({ name: n, system_prompt: p, provider: pr, model: m })
  }).then(() => {
    hideModal('mAgent');
    $('naN').value = '';
    $('naP').value = '';
    loadAgents();
    toast('Agent created','success');
  }).catch(e => {
    if (e.message !== 'Unauthorized') toast('Failed to create agent','error');
  });
}

function deleteAgent(id) {
  if (!confirm('Delete this agent?')) return;
  fetch('/api/agents/' + id, {
    method: 'DELETE',
    headers: { 'Authorization': 'Bearer ' + T, 'Content-Type': 'application/json' }
  }).then(r => {
    if (!r.ok) throw new Error();
    return r.json();
  }).then(() => {
    loadAgents();
    toast('Deleted','success');
  }).catch(() => toast('Failed','error'));
}

function confirmDeleteAgent(id) {
  const agent = allAgents.find(a => a.id === id);
  if (!agent) return;
  showConfirmDialog({
    title: 'Delete Agent',
    message: `Are you sure you want to delete "${agent.name}"? This action cannot be undone.`,
    confirmText: 'Delete',
    confirmClass: 'danger',
    onConfirm: () => deleteAgent(id)
  });
}

function editAgent(id) {
  const agent = allAgents.find(a => a.id === id);
  if (!agent) return;
  const tools = agent.tools ? (typeof agent.tools === 'string' ? JSON.parse(agent.tools || '[]') : agent.tools) : [];
  const content = `
    <div style="padding:4px 0">
      <div class="field">
        <label>Agent Name</label>
        <input class="inp" id="editAgentName" value="${esc(agent.name)}">
      </div>
      <div class="field">
        <label>System Prompt</label>
        <textarea class="inp" id="editAgentPrompt" rows="8" style="font-family:var(--fm);font-size:12px">${esc(agent.system_prompt || '')}</textarea>
      </div>
      <div class="field">
        <label>Temperature: <span id="editTempVal">${agent.temperature || 0.7}</span></label>
        <input type="range" min="0" max="2" step="0.1" value="${agent.temperature || 0.7}" class="slider" id="editAgentTemp" oninput="$('editTempVal').textContent=this.value">
      </div>
      <div class="field">
        <label>Max Tokens: <span id="editMaxVal">${agent.max_tokens || 4096}</span></label>
        <input type="range" min="256" max="8192" step="256" value="${agent.max_tokens || 4096}" class="slider" id="editAgentMax" oninput="$('editMaxVal').textContent=this.value">
      </div>
      <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:16px">
        <button class="btn btnG btnSM" onclick="closeWindow('edit-agent-${id}')">Cancel</button>
        <button class="btn btnP btnSM" onclick="saveAgentEdit('${id}')">Save Changes</button>
      </div>
    </div>
  `;
  const vw = window.innerWidth, vh = window.innerHeight;
  createWindow({
    id: 'edit-agent-' + id,
    title: 'Edit: ' + agent.name,
    icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>',
    content: content,
    width: 500,
    height: 550,
    x: (vw-500) / 2,
    y: (vh-550) / 2
  });
}

function saveAgentEdit(id) {
  const name = $('editAgentName').value.trim();
  const prompt = $('editAgentPrompt').value.trim();
  const temp = parseFloat($('editAgentTemp').value);
  const max = parseInt($('editAgentMax').value);
  if (!name) { toast('Name required','warning'); return; }
  const agent = allAgents.find(a => a.id === id);
  if (!agent) return;
  const updated = { ...agent, name, system_prompt: prompt, temperature: temp, max_tokens: max };
  fetch('/api/agents/' + id, {
    method: 'PUT',
    headers: { 'Authorization': 'Bearer ' + T, 'Content-Type': 'application/json' },
    body: JSON.stringify(updated)
  }).then(r => {
    if (!r.ok) throw new Error();
    return r.json();
  }).then(() => {
    closeWindow('edit-agent-' + id);
    loadAgents();
    toast('Agent updated','success');
  }).catch(() => toast('Failed to update','error'));
}

function createFromTemplate(id, name) {
  const template = allTemplates.find(t => t.id === id);
  if (!template) return;
  const icon = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 2v3M8 8v3M16 8v3"/></svg>';
  const content = `
    <div style="margin-bottom:16px"><label style="font-size:12px;font-weight:500;color:var(--tx2);display:block;margin-bottom:6px">Agent Name</label><input class="inp" id="tplName" value="${esc(name)}"></div>
    <div style="margin-bottom:16px"><label style="font-size:12px;font-weight:500;color:var(--tx2);display:block;margin-bottom:6px">Description</label><div style="font-size:13px;color:var(--tx2);line-height:1.5;padding:8px;background:var(--bg3);border-radius:8px;border:1px solid var(--bd)">${esc(template.description)}</div></div>
    <div style="margin-bottom:16px"><label style="font-size:12px;font-weight:500;color:var(--tx2);display:block;margin-bottom:6px">System Prompt</label><textarea class="inp" id="tplPrompt" rows="6" style="font-family:var(--fm);font-size:12px">${esc(template.system_prompt)}</textarea></div>
    <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:16px">
      <button class="btn btnG btnSM" onclick="closeWindow('tpl-${id}')">Cancel</button>
      <button class="btn btnP btnSM" onclick="confirmCreateTemplate('${id}')">Create Agent</button>
    </div>
  `;
  const vw = window.innerWidth, vh = window.innerHeight;
  createWindow({
    id: 'tpl-' + id,
    title: 'Create from Template: ' + name,
    icon: icon,
    content: content,
    width: 500,
    height: 500,
    x: (vw-500) / 2,
    y: (vh-500) / 2
  });
}

function confirmCreateTemplate(id) {
  const template = allTemplates.find(t => t.id === id);
  if (!template) return;
  const name = $('tplName').value.trim();
  const prompt = $('tplPrompt').value.trim();
  if (!name) { toast('Name required','warning'); return; }
  if (!prompt) { toast('System prompt required','warning'); return; }
  
  api('/api/templates/create', {
    method: 'POST',
    body: JSON.stringify({ template_id: id, name_override: name, prompt_override: prompt })
  }).then(() => {
    closeWindow('tpl-' + id);
    loadAgents();
    toast(name + ' created','success');
  }).catch(() => api('/api/templates/create', {
    method: 'POST',
    body: JSON.stringify({ template_id: id })
  }).then(() => {
    closeWindow('tpl-' + id);
    loadAgents();
    toast(name + ' created','success');
  }));
}

function openAgentWindow(agent) {
  const icon = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 2v3M8 8v3M16 8v3"/></svg>';
  const tools = agent.tools ? (typeof agent.tools === 'string' ? JSON.parse(agent.tools || '[]') : agent.tools) : [];
  const toolIcons = {
    'web_search': '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>',
    'calculator': '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="4" y="2" width="16" height="20" rx="2"/><line x1="8" y1="6" x2="16" y2="6"/></svg>',
    'execute_code': '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>',
    'generate_image': '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>'
  };
  const stats = agentStats[agent.id] || { messages: 0, avg_response: 0, success_rate: 0, tokens_used: 0, status: 'idle' };
  const messages = stats.messages;
  const avgResponse = stats.avg_response;
  const successRate = stats.success_rate;
  const tokensUsed = stats.tokens_used;
  const status = stats.status;
  const statusText = status === 'active' ? 'Active' : (status === 'idle' ? 'Idle' : 'Offline');
  const content = `
    <div class="windowToolbar" style="margin:-20px -20px 20px;padding:16px;background:var(--bg3);border-bottom:1px solid var(--bd)">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <div>
          <div style="font-size:16px;font-weight:700;margin-bottom:6px">${esc(agent.name)}</div>
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
            <div class="agStatusIndicator" style="position:static;padding:4px 10px">
              <div class="agStatusDot ${status}"></div>
              <span>${statusText}</span>
            </div>
            <span class="pill pA">${agent.provider || 'default'}</span>
            <span class="pill pN">temp ${agent.temperature || 0.7}</span>
          </div>
        </div>
        <div style="display:flex;gap:8px">
          <button class="btn btnS btnSM" onclick="quickChatAgent('${agent.id}')">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
            Open Chat
          </button>
        </div>
      </div>
    </div>
    
    <div class="agPerformance" style="margin-bottom:20px">
      <div class="agPerfItem">
        <div class="agPerfLabel">Messages</div>
        <div class="agPerfValue">${messages}</div>
        <div class="agPerfBar"><div class="agPerfBarFill" style="width:${Math.min(messages/2, 100)}%"></div></div>
      </div>
      <div class="agPerfItem">
        <div class="agPerfLabel">Avg Response</div>
        <div class="agPerfValue">${avgResponse}s</div>
        <div class="agPerfBar"><div class="agPerfBarFill" style="width:${Math.min(100-avgResponse*30, 100)}%"></div></div>
      </div>
      <div class="agPerfItem">
        <div class="agPerfLabel">Success Rate</div>
        <div class="agPerfValue">${successRate}%</div>
        <div class="agPerfBar"><div class="agPerfBarFill" style="width:${successRate}%"></div></div>
      </div>
      <div class="agPerfItem">
        <div class="agPerfLabel">Tokens Used</div>
        <div class="agPerfValue">${(tokensUsed/1000).toFixed(1)}K</div>
        <div class="agPerfBar"><div class="agPerfBarFill" style="width:${Math.min(tokensUsed/500, 100)}%"></div></div>
      </div>
    </div>
    
    <div style="margin-bottom:20px">
      <label style="font-size:12px;font-weight:600;color:var(--tx2);display:block;margin-bottom:8px;text-transform:uppercase;letter-spacing:0.5px">System Prompt</label>
      <textarea class="inp" rows="5" style="font-family:var(--fm);font-size:12px;line-height:1.6;background:var(--bg3)" readonly>${esc(agent.system_prompt)}</textarea>
    </div>
    
    ${tools.length ? `<div style="margin-bottom:20px">
      <label style="font-size:12px;font-weight:600;color:var(--tx2);display:block;margin-bottom:8px;text-transform:uppercase;letter-spacing:0.5px">Available Tools (${tools.length})</label>
      <div class="agTools" style="border:none;padding:0;margin:0">
        ${tools.map(t => `<div class="agTool">${toolIcons[t] || '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/></svg>'}<span>${t.replace(/_/g, ' ')}</span></div>`).join('')}
      </div>
    </div>` : ''}
    
    <div style="margin-bottom:20px">
      <label style="font-size:12px;font-weight:600;color:var(--tx2);display:block;margin-bottom:8px;text-transform:uppercase;letter-spacing:0.5px">Quick Chat</label>
      <div style="display:flex;gap:8px;margin-bottom:12px">
        <input class="inp" id="agentChatInput-${agent.id}" placeholder="Send a message to ${esc(agent.name)}…" onkeydown="if(event.key==='Enter')sendAgentChat('${agent.id}')">
        <button class="btn btnP btnSM" onclick="sendAgentChat('${agent.id}')">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
        </button>
      </div>
      <div id="agentChatHistory-${agent.id}" style="max-height:240px;overflow-y:auto;background:var(--bg3);border-radius:10px;padding:16px;border:1px solid var(--bd);min-height:100px;font-size:14px;line-height:1.6">
        <div style="color:var(--tx3);font-size:14px;text-align:center;padding:24px;line-height:1.6">Start a conversation with ${esc(agent.name)}</div>
      </div>
    </div>
    
    <div style="display:flex;gap:8px;justify-content:space-between;padding-top:16px;border-top:1px solid var(--bd)">
      <button class="btn btnD btnSM" onclick="deleteAgent('${agent.id}');closeWindow('agent-${agent.id}')">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
        Delete Agent
      </button>
      <button class="btn btnS btnSM" onclick="closeWindow('agent-${agent.id}')">Close</button>
    </div>
  `;
  const vw = window.innerWidth, vh = window.innerHeight;
  createWindow({ id: 'agent-' + agent.id, title: agent.name, icon: icon, content: content, width: 600, height: Math.min(700, vh-100), x: (vw-600) / 2, y: (vh-700) / 2 });
}

function sendAgentChat(agentId) {
  const input = document.getElementById('agentChatInput-' + agentId);
  const history = document.getElementById('agentChatHistory-' + agentId);
  if (!input || !input.value.trim()) return;
  const msg = input.value.trim();
  input.value = '';
  history.innerHTML += '<div style="padding:12px;margin-bottom:8px;background:var(--acS);border-radius:10px;font-size:14px;line-height:1.6"><strong style="color:var(--ac)">You:</strong> ' + esc(msg) + '</div>';
  history.innerHTML += '<div style="padding:12px;font-size:14px;color:var(--tx3);line-height:1.6" id="agentTyping-' + agentId + '"><em>Thinking...</em></div>';
  history.scrollTop = history.scrollHeight;
  api('/api/chat', { method: 'POST', body: JSON.stringify({ agent_id: agentId, message: msg }) }).then(r => {
    const typing = document.getElementById('agentTyping-' + agentId);
    if (typing) typing.remove();
    history.innerHTML += '<div style="padding:12px;margin-bottom:8px;background:var(--bg3);border-radius:10px;font-size:14px;line-height:1.6"><strong style="color:var(--gr)">Agent:</strong> ' + esc(r.response || 'No response') + '</div>';
    history.scrollTop = history.scrollHeight;
  }).catch(e => {
    const typing = document.getElementById('agentTyping-' + agentId);
    if (typing) typing.remove();
    history.innerHTML += '<div style="padding:12px;font-size:14px;color:var(--rd);line-height:1.6">Error sending message. Please try again.</div>';
    console.error('Chat error:', e);
  });
}

function filterAgents() {
  clearTimeout(filterDebounce);
  filterDebounce = setTimeout(() => {
    const q = $('agentSearch').value.toLowerCase();
    const cards = document.querySelectorAll('#myAgents .agCard');
    cards.forEach(c => { c.style.display = c.textContent.toLowerCase().includes(q) ? '' : 'none'; });
  }, 150);
}
