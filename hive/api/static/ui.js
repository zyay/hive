/* ═══ HIVE UI JAVASCRIPT ═══ */

// Global state
let T = null, U = null, N = null;
let currentRoom = null, currentConversation = null;
let ws = null, wsRetry = 0;
let unread = {};
let currentMessages = [];
let allAgents = [];
let allTemplates = [];
let agentFilter = 'All';
let mentionIdx = -1;
let mentionItems = [];
let autoRefreshInterval = null;
let agentStats = {};
let filterDebounce = null;
let windowZIndex = 1000;
let activeWindows = new Map();
let dragWindow = null, dragOffsetX = 0, dragOffsetY = 0;
let resizeWindow = null, resizeStartX = 0, resizeStartY = 0, resizeStartW = 0, resizeStartH = 0;
let allFiles = [];

// Helper functions
const $ = id => document.getElementById(id);
const esc = s => String(s||'').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":"&#39;"}[c]));

// API wrapper with error handling
const api = (url, options = {}) => {
  options.headers = options.headers || {};
  options.headers['Content-Type'] = 'application/json';
  if (T) options.headers['Authorization'] = 'Bearer ' + T;
  
  const isWrite = ['POST','PUT','DELETE','PATCH'].includes(options.method);
  const btn = isWrite ? document.querySelector('button[type="submit"]:focus, .btn:focus') : null;
  if (btn) { btn.disabled = true; btn.dataset.origText = btn.textContent; btn.textContent = 'Loading...'; }
  
  return fetch(url, options)
    .then(r => {
      if (!r.ok) {
        if (r.status === 401) { toast('Session expired, please login again','error'); logout(); throw new Error('Unauthorized'); }
        if (r.status === 404) throw new Error('Not found');
        if (r.status === 403) throw new Error('Permission denied');
        throw new Error('Request failed');
      }
      return r.json();
    })
    .catch(e => {
      if (e.message !== 'Unauthorized' && e.message !== 'Not found' && e.message !== 'Permission denied') {
        console.error('API Error:', e);
      }
      throw e;
    })
    .finally(() => {
      if (btn) { btn.disabled = false; btn.textContent = btn.dataset.origText || 'Submit'; }
    });
};

// Toast notifications
function toast(msg, type = 'info') {
  const icons = {
    info: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
    success: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
    warning: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
    error: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>'
  };
  
  const el = document.createElement('div');
  el.className = `t t${type[0].toUpperCase() + type.slice(1)}`;
  el.innerHTML = `<div class="tI">${icons[type] || icons.info}</div><div class="tC">${msg}</div><div class="tX" onclick="this.parentElement.remove()">✕</div>`;
  $('toastContainer').appendChild(el);
  setTimeout(() => { el.style.animation = 'slideIn 0.3s var(--ease) reverse'; setTimeout(() => el.remove(), 300); }, 4000);
}

// Confirm dialog
function showConfirmDialog(opts) {
  const { title, message, confirmText = 'Confirm', cancelText = 'Cancel', confirmClass = 'primary', onConfirm, onCancel } = opts;
  const overlay = document.createElement('div');
  overlay.className = 'confirmOverlay';
  overlay.innerHTML = `
    <div class="confirmDialog">
      <div class="confirmHeader">${title}</div>
      <div class="confirmMessage">${message}</div>
      <div class="confirmActions">
        <button class="btn btnG btnSM" onclick="this.closest('.confirmOverlay').remove();${onCancel ? '('+onCancel.toString()+')()' : ''}">${cancelText}</button>
        <button class="btn btn${confirmClass.charAt(0).toUpperCase()+confirmClass.slice(1)} btnSM" id="confirmBtn">${confirmText}</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
  const btn = overlay.querySelector('#confirmBtn');
  btn.onclick = () => { overlay.remove(); if (onConfirm) onConfirm(); };
  overlay.onclick = e => { if (e.target === overlay) { overlay.remove(); if (onCancel) onCancel(); } };
}

// Loading overlay
function showLoading(text = 'Loading...') {
  const overlay = document.createElement('div');
  overlay.className = 'loadingOverlay';
  overlay.id = 'globalLoading';
  overlay.innerHTML = `<div class="loadingSpinner"></div><div class="loadingText">${text}</div>`;
  document.body.appendChild(overlay);
}

function hideLoading() {
  const overlay = document.getElementById('globalLoading');
  if (overlay) overlay.remove();
}

// Authentication
function login() {
  const username = $('authUsername').value.trim();
  const password = $('authPassword').value.trim();
  if (!username || !password) { toast('Please enter username and password','warning'); return; }
  
  showLoading('Signing in...');
  api('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password })
  }).then(data => {
    T = data.token;
    U = data.user_id;
    N = data.name;
    hideLoading();
    enterApp();
  }).catch(e => {
    hideLoading();
    toast('Login failed: ' + e.message,'error');
  });
}

function register() {
  const username = $('authUsername').value.trim();
  const password = $('authPassword').value.trim();
  if (!username || !password) { toast('Please enter username and password','warning'); return; }
  if (username.length < 3) { toast('Username must be at least 3 characters','warning'); return; }
  if (password.length < 6) { toast('Password must be at least 6 characters','warning'); return; }
  
  showLoading('Creating account...');
  api('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify({ username, password, name: username })
  }).then(data => {
    T = data.token;
    U = data.user_id;
    N = data.name;
    hideLoading();
    enterApp();
    toast('Account created successfully','success');
  }).catch(e => {
    hideLoading();
    toast('Registration failed: ' + e.message,'error');
  });
}

function logout() {
  showConfirmDialog({
    title: 'Sign Out',
    message: 'Are you sure you want to sign out? Your session will be cleared.',
    confirmText: 'Sign Out',
    confirmClass: 'danger',
    onConfirm: () => {
      T = null; U = null; N = null;
      if (ws) ws.close();
      stopAutoRefresh();
      activeWindows.forEach((w, id) => closeWindow(id));
      localStorage.clear();
      location.reload();
    }
  });
}

function enterApp() {
  localStorage.setItem('ht', T);
  localStorage.setItem('hu', U);
  localStorage.setItem('hn', N);
  $('authScreen').style.display = 'none';
  $('userName').textContent = N;
  $('userAvatar').textContent = N.charAt(0).toUpperCase();
  $('profileAvatar').textContent = N.charAt(0).toUpperCase();
  $('profileName').textContent = N;
  $('profileUsername').textContent = '@' + U;
  loadRooms();
  loadProviders();
  if (!localStorage.getItem('hive_welcome_seen')) { $('welcomeBanner').style.display = 'block'; }
  if (!localStorage.getItem('hive_tutorial_done')) setTimeout(startTutorial, 800);
  const savedAccent = localStorage.getItem('hive_accent');
  if (savedAccent) document.documentElement.style.setProperty('--ac', savedAccent);
  startAutoRefresh();
}

// Auto-refresh
function startAutoRefresh() {
  if (autoRefreshInterval) clearInterval(autoRefreshInterval);
  autoRefreshInterval = setInterval(() => {
    const activeView = document.querySelector('.view.active');
    if (!activeView) return;
    const viewId = activeView.id;
    if (viewId === 'view-tasks') loadTasks();
    else if (viewId === 'view-files') loadFiles();
    else if (viewId === 'view-dashboard') loadDashboard();
    else if (viewId === 'view-agents') loadAgents();
    else if (viewId === 'view-settings') loadKeys();
  }, 10000);
}

function stopAutoRefresh() {
  if (autoRefreshInterval) { clearInterval(autoRefreshInterval); autoRefreshInterval = null; }
}

// Navigation
function showView(v) {
  document.querySelectorAll('.view').forEach(view => view.classList.remove('active'));
  document.querySelectorAll('.ni').forEach(item => item.classList.remove('active'));
  const view = $('view-' + v);
  if (view) {
    view.classList.add('active');
    view.style.animation = 'none';
    view.offsetHeight;
    view.style.animation = 'viewIn 0.35s var(--ease)';
  }
  const navItem = document.querySelector(`.ni[onclick*="${v}"]`);
  if (navItem) navItem.classList.add('active');
  
  if (v === 'agents') loadAgents();
  if (v === 'tasks') loadTasks();
  if (v === 'files') loadFiles();
  if (v === 'dashboard') loadDashboard();
  if (v === 'settings') { loadKeys(); loadProfileInfo(); }
  
  document.querySelector('.sidebar').classList.remove('open');
}

// Rooms
function loadRooms() {
  api('/api/rooms?user_id=' + U).then(r => {
    $('roomList').innerHTML = r.map(x => {
      const b = unread[x.id] ? `<div class="riB">${unread[x.id]}</div>` : '';
      return `<div class="ri${currentRoom === x.id ? ' active' : ''}" onclick="openRoom('${x.id}','${esc(x.name||x.id)}')">
        <div class="riI"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg></div>
        <div class="riC"><div class="riT">${esc(x.name||x.id)}</div><div class="riM">${x.type}</div></div>
        ${b}
        <button class="btnI riDel" onclick="event.stopPropagation();deleteRoom('${x.id}')" title="Delete">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
        </button>
      </div>`;
    }).join('') || '<div style="padding:16px;text-align:center;color:var(--tx3);font-size:12px">No rooms yet</div>';
  });
}

function openRoom(id, name) {
  currentRoom = id;
  unread[id] = 0;
  $('chatTitle').textContent = name;
  $('chatSub').textContent = '';
  loadRooms();
  $('composer').style.display = 'block';
  connectWS(id);
  api('/api/rooms/' + id + '/messages').then(m => {
    currentMessages = m;
    $('chatMessages').innerHTML = m.map(rMsg).join('') || '<div class="empty"><div class="eT">No messages</div><div class="eD">Send the first message</div></div>';
    scrollChatToBottom();
  });
}

function rMsg(x) {
  const u = x.sender_id === U;
  const content = u ? esc(x.content).replace(/\n/g,'<br>') : rMd(x.content);
  const mentions = x.content.match(/@\w+/g);
  let display = content;
  if (mentions) mentions.forEach(m => {
    const agentName = m.substring(1);
    const agent = allAgents.find(a => a.name === agentName || a.name.toLowerCase() === agentName.toLowerCase());
    const tooltip = agent ? `${agent.name} · ${agent.provider||'default'} · ${agent.tools?JSON.parse(agent.tools||'[]').length:0} tools` : '';
    display = display.replace(new RegExp(m.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'),'g'),
      `<span class="mention" title="${esc(tooltip)}" style="cursor:pointer" onclick="event.stopPropagation();${agent ? `openAgentById('${agent.id}')` : ''}" >${m}</span>`);
  });
  const time = x.created_at ? fmtTime(x.created_at) : '';
  return `<div class="msg ${u?'msgU':'msgA'}"><div class="mA">${u?N?.charAt(0).toUpperCase()||'U':'A'}</div><div><div class="mB">${display}</div><div class="mTime">${time}</div></div></div>`;
}

function createRoom() {
  const n = $('nrN').value.trim();
  const t = $('nrT').value;
  if (!n) { toast('Room name is required','warning'); $('nrN').focus(); return; }
  if (n.length < 2) { toast('Room name must be at least 2 characters','warning'); $('nrN').focus(); return; }
  if (n.length > 50) { toast('Room name must be less than 50 characters','warning'); $('nrN').focus(); return; }
  
  api('/api/rooms?user_id='+U, {
    method: 'POST',
    body: JSON.stringify({ name: n, type: t })
  }).then(() => {
    hideModal('mRoom');
    $('nrN').value = '';
    loadRooms();
    toast('Room created','success');
  }).catch(e => {
    if (e.message !== 'Unauthorized') toast('Failed to create room','error');
  });
}

function deleteRoom(id) {
  if (!confirm('Delete this room?')) return;
  fetch('/api/rooms/' + id + '?user_id=' + U, {
    method: 'DELETE',
    headers: { 'Authorization': 'Bearer ' + T, 'Content-Type': 'application/json' }
  }).then(r => {
    if (!r.ok) throw new Error();
    return r.json();
  }).then(() => {
    if (currentRoom === id) {
      currentRoom = null;
      $('chatMessages').innerHTML = '<div class="empty"><div class="eT">Select a conversation</div></div>';
      $('composer').style.display = 'none';
      $('chatTitle').textContent = 'Select a conversation';
    }
    loadRooms();
    toast('Deleted','success');
  }).catch(() => toast('Failed','error'));
}

// WebSocket
function connectWS(id) {
  if (ws) ws.close();
  const p = location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(p + '//' + location.host + '/ws/' + id + '?token=' + T);
  
  ws.onopen = () => { wsRetry = 0; console.log('WebSocket connected'); };
  
  ws.onclose = () => {
    console.log('WebSocket disconnected, retrying...');
    if (T && currentRoom && wsRetry < 10) {
      const delay = Math.min(1000 * Math.pow(2, wsRetry++), 30000);
      setTimeout(() => { if (currentRoom) connectWS(currentRoom); }, delay);
    }
  };
  
  ws.onerror = e => { console.error('WebSocket error:', e); };
  
  ws.onmessage = e => {
    try {
      const d = JSON.parse(e.data);
      if (d.type === 'new_message') {
        currentMessages.push(d.message);
        const msgEl = rMsg(d.message);
        $('chatMessages').innerHTML += msgEl;
        scrollChatToBottom();
        $('processingIndicator').style.display = 'none';
        if (d.message.sender_id !== U && currentRoom !== id) {
          unread[id] = (unread[id] || 0) + 1;
          loadRooms();
          if (!document.hasFocus()) playPing();
          updatePageTitle();
        }
      } else if (d.type === 'typing') {
        $('processingIndicator').style.display = 'flex';
        clearTimeout(window._tt);
        window._tt = setTimeout(() => { $('processingIndicator').style.display = 'none'; }, 3000);
      }
    } catch (err) {
      console.error('Failed to parse WebSocket message:', err);
    }
  };
}

function sendMessage() {
  const v = $('chatInput').value.trim();
  if (!v || !currentRoom) return;
  $('chatInput').value = '';
  $('mentionDropdown').classList.remove('show');
  $('processingIndicator').style.display = 'flex';
  api('/api/rooms/' + currentRoom + '/messages?user_id=' + U, {
    method: 'POST',
    body: JSON.stringify({ content: v })
  });
}

// @Mention system
function handleMentionInput() {
  const inp = $('chatInput');
  const val = inp.value;
  const pos = inp.selectionStart;
  const before = val.substring(0, pos);
  const atMatch = before.match(/@(\w*)$/);
  if (!atMatch) { $('mentionDropdown').classList.remove('show'); return; }
  
  const q = atMatch[1].toLowerCase();
  mentionItems = allAgents.filter(a => a.name.toLowerCase().includes(q) || a.id.toLowerCase().includes(q));
  if (!mentionItems.length) { $('mentionDropdown').classList.remove('show'); return; }
  
  mentionIdx = 0;
  const dd = $('mentionDropdown');
  dd.innerHTML = mentionItems.map((a, i) => {
    const tools = a.tools ? (typeof a.tools === 'string' ? JSON.parse(a.tools || '[]') : a.tools) : [];
    const status = agentStats[a.id]?.status || 'idle';
    const statusText = status === 'active' ? 'Ready' : 'Idle';
    return `<div class="mentionItem${i === mentionIdx ? ' sel' : ''}" onmousedown="event.preventDefault();selectMention(allAgents[${allAgents.indexOf(a)}])">
      <div style="display:flex;align-items:center;gap:10px;flex:1;min-width:0">
        <div style="position:relative">
          <div class="miI">${a.name.charAt(0).toUpperCase()}</div>
          <div class="agStatusDot ${status}" style="position:absolute;bottom:-2px;right:-2px;width:8px;height:8px;border:2px solid var(--bg2)"></div>
        </div>
        <div style="flex:1;min-width:0">
          <div style="display:flex;align-items:center;gap:6px">
            <div class="miN" style="font-weight:600">${esc(a.name)}</div>
            <div class="agStatusIndicator" style="position:static;padding:2px 6px;font-size:9px">${statusText}</div>
          </div>
          <div class="miD" style="margin-top:3px">${a.provider||'default'} · temp ${a.temperature||0.7}</div>
          ${tools.length ? `<div style="display:flex;gap:4px;margin-top:5px;flex-wrap:wrap">${tools.slice(0,2).map(t => `<span style="font-size:9px;padding:2px 5px;background:var(--bg4);border-radius:3px;color:var(--tx3)">${t.replace(/_/g,' ')}</span>`).join('')}${tools.length > 2 ? `<span style="font-size:9px;padding:2px 5px;color:var(--tx4)">+${tools.length-2}</span>` : ''}</div>` : ''}
        </div>
      </div>
    </div>`;
  }).join('');
  dd.classList.add('show');
}

function renderMentionSel() {
  const items = document.querySelectorAll('.mentionItem');
  items.forEach((el, i) => el.classList.toggle('sel', i === mentionIdx));
}

function selectMention(agent) {
  const inp = $('chatInput');
  const val = inp.value;
  const pos = inp.selectionStart;
  const before = val.substring(0, pos);
  const after = val.substring(pos);
  const newBefore = before.replace(/@\w*$/, '@' + agent.name + ' ');
  inp.value = newBefore + after;
  inp.focus();
  inp.selectionStart = inp.selectionEnd = newBefore.length;
  $('mentionDropdown').classList.remove('show');
}

// Agents
function loadAgents() {
  api('/api/agents').then(a => { allAgents = a; $('agentCount').textContent = a.length; renderMyAgents(); });
  api('/api/templates').then(t => { allTemplates = t; $('templateCount').textContent = t.length; renderTemplateGrid(); });
  api('/api/agents/stats').then(s => { agentStats = s; }).catch(() => {});
}

function renderMyAgents() {
  const el = $('myAgents');
  if (!allAgents.length) {
    el.innerHTML = '<div class="emptyState"><div class="emptyStateIcon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 2v3M8 8v3M16 8v3"/></svg></div><div class="emptyStateTitle">No agents yet</div><div class="emptyStateDesc">Create your first agent or choose from the templates below to get started.</div></div>';
    return;
  }
  
  api('/api/agents/stats').then(stats => {
    el.innerHTML = allAgents.map(x => {
      const prompt = (x.system_prompt || '').substring(0, 140);
      const tools = x.tools ? (typeof x.tools === 'string' ? JSON.parse(x.tools || '[]') : x.tools) : [];
      const toolIcons = {
        'web_search': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>',
        'calculator': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="4" y="2" width="16" height="20" rx="2"/><line x1="8" y1="6" x2="16" y2="6"/></svg>',
        'execute_code': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>',
        'generate_image': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>'
      };
      
      const agentStats = stats[x.id] || { messages: 0, avg_response: 0, success_rate: 0, tokens_used: 0, status: 'idle' };
      const status = agentStats.status;
      const statusText = status === 'active' ? 'Ready' : (status === 'idle' ? 'Idle' : 'Offline');
      const messages = agentStats.messages;
      const avgResponse = agentStats.avg_response.toFixed(1);
      const successRate = agentStats.success_rate;
      const tokensUsed = agentStats.tokens_used;
      const agentIcon = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 2v3M8 8v3M16 8v3"/></svg>';
      
      return `<div class="agCard${status === 'active' ? ' agCardFeatured' : ''}" onclick="openAgentById('${x.id}')">
        <div class="agStatusIndicator">
          <div class="agStatusDot ${status}"></div>
          <span>${statusText}</span>
        </div>
        <div class="agActions">
          <button class="agActionBtn" onclick="event.stopPropagation();editAgent('${x.id}')" title="Edit">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
          </button>
          <button class="agActionBtn danger" onclick="event.stopPropagation();confirmDeleteAgent('${x.id}')" title="Delete">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
          </button>
        </div>
        <div class="agIc" style="background:var(--bg4);border:1px solid var(--bd2);color:var(--tx)">${agentIcon}</div>
        <div class="agN">${esc(x.name)}</div>
        <div class="agD">${esc(prompt)}${(x.system_prompt || '').length > 140 ? '...' : ''}</div>
        <div class="agStats">
          <div class="agStat">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
            <span class="agStatValue">${messages}</span>
            <span>messages</span>
          </div>
          <div class="agStat">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            <span class="agStatValue">${avgResponse}s</span>
            <span>avg</span>
          </div>
          <div class="agStat">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
            <span class="agStatValue">${successRate}%</span>
            <span>success</span>
          </div>
        </div>
        <div class="agPerformance">
          <div class="agPerfItem">
            <div class="agPerfLabel">Tokens Used</div>
            <div class="agPerfValue">${(tokensUsed/1000).toFixed(1)}K</div>
            <div class="agPerfBar"><div class="agPerfBarFill" style="width:${Math.min(tokensUsed/500, 100)}%"></div></div>
          </div>
          <div class="agPerfItem">
            <div class="agPerfLabel">Provider</div>
            <div class="agPerfValue" style="font-size:13px">${esc(x.provider || 'default')}</div>
          </div>
        </div>
        ${tools.length ? `<div class="agTools">
          ${tools.slice(0, 3).map(t => `<div class="agTool">${toolIcons[t] || '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/></svg>'}<span>${t.replace(/_/g,' ')}</span></div>`).join('')}
          ${tools.length > 3 ? `<div class="agTool">+${tools.length-3}</div>` : ''}
        </div>` : ''}
        <div class="agQuickActions">
          <button class="agQuickBtn" onclick="event.stopPropagation();quickChatAgent('${x.id}')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
            Chat
          </button>
          <button class="agQuickBtn" onclick="event.stopPropagation();openAgentById('${x.id}')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
            Details
          </button>
        </div>
      </div>`;
    }).join('');
  }).catch(() => {
    el.innerHTML = '<div class="emptyState"><div class="emptyStateTitle">Error loading agent stats</div></div>';
  });
}

function openAgentById(id) {
  const agent = allAgents.find(a => a.id === id);
  if (agent) openAgentWindow(agent);
}

function quickChatAgent(id) {
  const agent = allAgents.find(a => a.id === id);
  if (!agent) return;
  showLoading('Opening chat with ' + agent.name + '...');
  api('/api/rooms?user_id=' + U).then(r => {
    const existingRoom = r.find(room => room.name === agent.name + ' Chat' || room.members?.includes(id));
    if (existingRoom) {
      showView('chat');
      openRoom(existingRoom.id, existingRoom.name);
      hideLoading();
    } else {
      api('/api/rooms?user_id=' + U, {
        method: 'POST',
        body: JSON.stringify({ name: agent.name + ' Chat', type: 'dm', members: [id] })
      }).then(newRoom => {
        showView('chat');
        openRoom(newRoom.id, newRoom.name);
        hideLoading();
        toast('Started chat with ' + agent.name, 'success');
      }).catch(e => {
        hideLoading();
        toast('Failed to create chat room', 'error');
        console.error('Failed to create room:', e);
      });
    }
  }).catch(e => {
    hideLoading();
    toast('Failed to load rooms', 'error');
    console.error('Failed to load rooms:', e);
  });
}

// Placeholder for remaining functions - file is too long, will split into multiple files
// Continue in ui-agents.js, ui-tasks.js, ui-files.js, etc.

// Initialize on load
window.addEventListener('DOMContentLoaded', () => {
  if (localStorage.getItem('ht')) {
    T = localStorage.getItem('ht');
    U = localStorage.getItem('hu');
    N = localStorage.getItem('hn');
    enterApp();
  }
});
