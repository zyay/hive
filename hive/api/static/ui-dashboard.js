/* ═══ DASHBOARD MODULE ═══ */

function loadDashboard() {
  api('/api/usage/summary').then(s => {
    const calls = s.total_calls || 0;
    const tokens = (s.total_tokens_in || 0) + (s.total_tokens_out || 0);
    const latency = s.avg_latency_ms || 0;
    
    $('dashStats').innerHTML = [
      { v: calls, l: 'Total Calls', c: 'ac', icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>' },
      { v: tokens, l: 'Tokens Used', c: 'gr', icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 7 4 4 20 4 20 7"/><line x1="9" y1="20" x2="15" y2="20"/><line x1="12" y1="4" x2="12" y2="20"/></svg>' },
      { v: (latency/1000).toFixed(2) + 's', l: 'Avg Latency', c: 'yl', icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>' },
      { v: allAgents.length, l: 'Active Agents', c: 'ac', icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>' }
    ].map(x => `<div class="sc"><div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;color:var(--${x.c})">${x.icon}</div><div class="sv" data-count="${typeof x.v === 'number' ? x.v : 0}" style="-webkit-text-fill-color:var(--${x.c})">${x.v}</div><div class="sl">${x.l}</div></div>`).join('');
    animateCounters();
  });
  
  // Load agents for dashboard
  api('/api/agents').then(a => {
    $('dashAgents').innerHTML = a.slice(0, 6).map(ag => {
      const status = agentStats[ag.id]?.status || 'idle';
      return `<div style="padding:12px;background:var(--bg4);border:1px solid var(--bd);border-radius:var(--r8);display:flex;align-items:center;gap:10px;cursor:pointer" onclick="showView('agents')">
        <div style="width:32px;height:32px;border-radius:var(--r8);background:var(--bg3);display:flex;align-items:center;justify-content:center;color:var(--ac)"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 2v3M8 8v3M16 8v3"/></svg></div>
        <div style="flex:1;min-width:0">
          <div style="font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(ag.name)}</div>
          <div style="font-size:11px;color:var(--tx3)">${ag.provider || 'default'}</div>
        </div>
        <div class="agStatusDot ${status}"></div>
      </div>`;
    }).join('') || '<div style="color:var(--tx3);text-align:center;padding:20px">No agents yet</div>';
  });
  
  // Load recent messages
  api('/api/rooms?user_id=' + U).then(rooms => {
    const recent = rooms.slice(0, 5);
    $('dashRecent').innerHTML = recent.map(r => {
      return `<div style="padding:12px;background:var(--bg4);border:1px solid var(--bd);border-radius:var(--r8);cursor:pointer;display:flex;align-items:center;gap:10px" onclick="showView('chat');openRoom('${r.id}','${esc(r.name || r.id)}')">
        <div style="width:32px;height:32px;border-radius:var(--r8);background:var(--acS);color:var(--ac);display:flex;align-items:center;justify-content:center"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg></div>
        <div style="flex:1;min-width:0">
          <div style="font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(r.name || r.id)}</div>
          <div style="font-size:11px;color:var(--tx3)">${r.type}</div>
        </div>
      </div>`;
    }).join('') || '<div style="color:var(--tx3);text-align:center;padding:20px">No conversations yet</div>';
  });
  
  // Activity heatmap - real data
  loadActivityHeatmap();
}

function loadActivityHeatmap() {
  api('/api/usage/history?days=7').then(history => {
    const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    const hours = Array.from({ length: 24 }, (_, i) => i);
    
    let maxCalls = 1;
    history.forEach(h => {
      if (h.calls > maxCalls) maxCalls = h.calls;
    });
    
    const heatmapEl = $('dashHeatmap');
    if (!heatmapEl) return;
    
    heatmapEl.innerHTML = `
      <div style="display:flex;gap:2px;align-items:flex-end;height:120px">
        ${days.map((day, di) => `
          <div style="flex:1;display:flex;flex-direction:column;gap:2px">
            ${hours.slice(0, 12).map(h => {
              const data = history.find(item => item.day === di && item.hour === h);
              const calls = data ? data.calls : 0;
              const intensity = Math.min(calls / maxCalls, 1);
              const bg = intensity > 0 ? `rgba(59,130,246,${0.2 + intensity * 0.8})` : 'var(--bg4)';
              return `<div style="height:8px;background:${bg};border-radius:2px" title="${day} ${h}:00 - ${calls} calls"></div>`;
            }).join('')}
            <div style="font-size:9px;color:var(--tx3);text-align:center;margin-top:4px">${day}</div>
          </div>
        `).join('')}
      </div>
    `;
  }).catch(() => {
    const heatmapEl = $('dashHeatmap');
    if (heatmapEl) {
      heatmapEl.innerHTML = '<div style="color:var(--tx3);text-align:center;padding:20px;font-size:12px">No activity data available</div>';
    }
  });
}
