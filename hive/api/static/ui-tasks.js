/* ═══ TASKS MODULE ═══ */

function loadTasks() {
  api('/api/tasks/stats').then(s => {
    $('taskStats').innerHTML = [
      { v: s.pending || 0, l: 'Pending', c: 'yl', icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>' },
      { v: s.running || 0, l: 'Running', c: 'ac', icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>' },
      { v: s.completed || 0, l: 'Completed', c: 'gr', icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>' },
      { v: s.failed || 0, l: 'Failed', c: 'rd', icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>' }
    ].map(x => `<div class="sc"><div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;color:var(--${x.c})">${x.icon}</div><div class="sv" data-count="${x.v}" style="-webkit-text-fill-color:var(--${x.c})">0</div><div class="sl">${x.l}</div></div>`).join('');
    animateCounters();
  });
  api('/api/tasks/queue').then(q => {
    $('taskActiveCount').textContent = q.length;
    $('taskQueue').innerHTML = q.map(t => renderTaskCard(t)).join('') || '<div class="emptyState"><div class="emptyStateIcon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg></div><div class="emptyStateTitle">No active tasks</div><div class="emptyStateDesc">Tasks will appear here when agents are processing work</div></div>';
  });
  api('/api/tasks/history').then(h => {
    $('taskHistoryCount').textContent = h.length;
    $('taskHistory').innerHTML = h.slice(0, 20).map(t => renderTaskCard(t)).join('') || '<div class="emptyState"><div class="emptyStateIcon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg></div><div class="emptyStateTitle">No history yet</div><div class="emptyStateDesc">Completed tasks will be logged here</div></div>';
  });
}

function renderTaskCard(t) {
  let progress = 0;
  if (t.status === 'completed') {
    progress = 100;
  } else if (t.status === 'running' && t.created_at) {
    const elapsed = (Date.now() / 1000 - t.created_at);
    const maxTime = 300;
    progress = Math.min(95, Math.floor((elapsed / maxTime) * 100));
  } else if (t.status === 'failed') {
    progress = t.progress || 0;
  } else if (t.status === 'pending') {
    progress = 0;
  }
  const agent = allAgents.find(a => a.id === t.agent_id);
  const icon = t.status === 'completed' ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>' :
    t.status === 'running' ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>' :
      t.status === 'failed' ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>' :
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>';
  return `<div class="taskCard">
    <div class="taskCardActions">
      ${t.status === 'pending' ? `<button class="agActionBtn danger" onclick="event.stopPropagation();cancelTask('${t.id}')" title="Cancel"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>` : ''}
    </div>
    <div class="taskCardHeader">
      <div class="taskCardTitle">${esc(t.title)}</div>
      <div class="taskCardStatus ${t.status}">${icon}<span>${t.status}</span></div>
    </div>
    ${t.description ? `<div style="font-size:12px;color:var(--tx2);margin-bottom:12px;line-height:1.5">${esc(t.description)}</div>` : ''}
    <div class="taskCardMeta">
      ${agent ? `<div class="taskCardMetaItem"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 2v3M8 8v3M16 8v3"/></svg><span>${esc(agent.name)}</span></div>` : ''}
      ${t.created_at ? `<div class="taskCardMetaItem"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg><span>${fmtTime(t.created_at)}</span></div>` : ''}
      ${t.template ? `<div class="taskCardMetaItem"><span class="pill pN">${t.template}</span></div>` : ''}
    </div>
    ${t.status === 'running' ? `<div class="taskProgressBar"><div class="taskProgressBarFill" style="width:${progress}%"></div></div>` : ''}
    ${t.result ? `<div style="margin-top:12px;padding:10px;background:var(--bg3);border-radius:8px;font-size:11px;color:var(--tx2);line-height:1.5"><strong>Result:</strong> ${esc(t.result).substring(0, 200)}${t.result.length > 200 ? '...' : ''}</div>` : ''}
  </div>`;
}

function createTask() {
  const t = $('ntT').value.trim();
  const d = $('ntD').value.trim();
  const a = $('ntA').value;
  if (!t) { toast('Title is required', 'warning'); $('ntT').focus(); return; }
  if (t.length < 3) { toast('Title must be at least 3 characters', 'warning'); $('ntT').focus(); return; }
  if (!a) { toast('Agent is required', 'warning'); $('ntA').focus(); return; }
  api('/api/tasks', {
    method: 'POST',
    body: JSON.stringify({ title: t, description: d, agent_id: a })
  }).then(() => {
    hideModal('mTask');
    $('ntT').value = '';
    $('ntD').value = '';
    loadTasks();
    toast('Task created', 'success');
  }).catch(e => {
    if (e.message !== 'Unauthorized') toast('Failed to create task', 'error');
  });
}

function cancelTask(id) {
  fetch('/api/tasks/' + id + '/cancel', {
    method: 'POST',
    headers: { 'Authorization': 'Bearer ' + T }
  }).then(r => {
    if (r.ok) { loadTasks(); toast('Task cancelled', 'success'); } else toast('Failed', 'error');
  }).catch(() => toast('Failed', 'error'));
}
