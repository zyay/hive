/* ═══ SETTINGS MODULE ═══ */

function loadKeys() {
  api('/api/users/keys?user_id=' + U).then(k => {
    $('keysList').innerHTML = k.map(x => `<div class="settingsCard" style="padding:14px;display:flex;align-items:center;justify-content:space-between">
      <div>
        <div style="font-size:13px;font-weight:600">${esc(x.provider)}</div>
        <div style="font-size:11px;color:var(--tx3)">${esc(x.api_key?.substring(0, 20) || '****')}...</div>
      </div>
      <button class="btn btnG btnSM" onclick="deleteKey('${x.provider}')">Delete</button>
    </div>`).join('') || '<div style="color:var(--tx3);text-align:center;padding:20px">No API keys saved</div>';
  });
}

function saveKey() {
  const p = $('keyProvider').value;
  const k = $('keyValue').value;
  if (!k) { toast('API key is required', 'warning'); return; }
  if (k.length < 10) { toast('API key seems too short', 'warning'); return; }
  
  showLoading('Saving API key...');
  api('/api/users/keys?user_id=' + U, {
    method: 'POST',
    body: JSON.stringify({ provider: p, api_key: k })
  }).then(() => {
    hideLoading();
    $('keyValue').value = '';
    loadKeys();
    toast('Key saved', 'success');
  }).catch(e => {
    hideLoading();
    toast('Failed to save key', 'error');
  });
}

function deleteKey(provider) {
  showConfirmDialog({
    title: 'Delete API Key',
    message: `Are you sure you want to delete the API key for ${provider}?`,
    confirmText: 'Delete',
    confirmClass: 'danger',
    onConfirm: () => {
      fetch('/api/users/keys/' + provider + '?user_id=' + U, {
        method: 'DELETE',
        headers: { 'Authorization': 'Bearer ' + T }
      }).then(r => {
        if (r.ok) { loadKeys(); toast('Key deleted', 'success'); } else toast('Failed', 'error');
      }).catch(() => toast('Failed', 'error'));
    }
  });
}

function loadProviders() {
  api('/api/providers').then(p => {
    const providers = ['anthropic', 'openai', 'openrouter', 'ollama'];
    const html = providers.map(pr => `<option value="${pr}">${pr.charAt(0).toUpperCase() + pr.slice(1)}</option>`).join('');
    
    const providerSelects = ['keyProvider', 'naPr'];
    providerSelects.forEach(id => {
      const el = $(id);
      if (el) el.innerHTML = html;
    });
  }).catch(() => {});
}

function loadProfileInfo() {
  $('profileAvatar').textContent = N ? N.charAt(0).toUpperCase() : 'U';
  $('profileName').textContent = N || 'User';
  $('profileUsername').textContent = '@' + (U || 'user');
  
  $('settingsInfoGrid').innerHTML = `
    <div class="settingsInfoItem">
      <div class="settingsInfoLabel">User ID</div>
      <div class="settingsInfoValue">${esc(U || 'N/A')}</div>
    </div>
    <div class="settingsInfoItem">
      <div class="settingsInfoLabel">Display Name</div>
      <div class="settingsInfoValue">${esc(N || 'N/A')}</div>
    </div>
    <div class="settingsInfoItem">
      <div class="settingsInfoLabel">Username</div>
      <div class="settingsInfoValue">@${esc(U || 'N/A')}</div>
    </div>
    <div class="settingsInfoItem">
      <div class="settingsInfoLabel">Session</div>
      <div class="settingsInfoValue">Active</div>
    </div>
  `;
}

// Settings navigation
function showSettingsPanel(panel) {
  document.querySelectorAll('.settingsNavItem').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.settingsPanel').forEach(el => el.classList.remove('active'));
  
  const navItem = document.querySelector(`.settingsNavItem[data-panel="${panel}"]`);
  const panelEl = $(panel);
  
  if (navItem) navItem.classList.add('active');
  if (panelEl) panelEl.classList.add('active');
}

// Appearance settings
function setAccentColor(color) {
  document.documentElement.style.setProperty('--ac', color);
  localStorage.setItem('hive_accent', color);
  
  document.querySelectorAll('.colorSwatch').forEach(el => {
    el.classList.toggle('active', el.dataset.color === color);
  });
  
  toast('Accent color updated', 'success');
}

function loadAccentColor() {
  const saved = localStorage.getItem('hive_accent');
  if (saved) {
    document.documentElement.style.setProperty('--ac', saved);
    document.querySelectorAll('.colorSwatch').forEach(el => {
      el.classList.toggle('active', el.dataset.color === saved);
    });
  }
}

// Notification settings
function toggleNotification(type) {
  const toggle = $(type + 'Toggle');
  if (!toggle) return;
  
  toggle.classList.toggle('active');
  const enabled = toggle.classList.contains('active');
  localStorage.setItem('hive_notify_' + type, enabled);
  toast((enabled ? 'Enabled' : 'Disabled') + ' notifications', 'success');
}

function loadNotificationSettings() {
  ['desktop', 'sound', 'badge'].forEach(type => {
    const toggle = $(type + 'Toggle');
    if (!toggle) return;
    const enabled = localStorage.getItem('hive_notify_' + type) !== 'false';
    if (enabled) toggle.classList.add('active');
  });
}

// Data export
function exportData() {
  showLoading('Preparing export...');
  
  const data = {
    user: { id: U, name: N, username: U },
    agents: allAgents,
    rooms: [],
    messages: [],
    files: allFiles,
    settings: {
      accent: localStorage.getItem('hive_accent'),
      notifications: {
        desktop: localStorage.getItem('hive_notify_desktop'),
        sound: localStorage.getItem('hive_notify_sound'),
        badge: localStorage.getItem('hive_notify_badge')
      }
    },
    exported_at: new Date().toISOString()
  };
  
  api('/api/rooms?user_id=' + U).then(rooms => {
    data.rooms = rooms;
    
    const promises = rooms.map(r =>
      api('/api/rooms/' + r.id + '/messages').then(msgs => {
        data.messages.push({ room_id: r.id, messages: msgs });
      })
    );
    
    return Promise.all(promises);
  }).then(() => {
    hideLoading();
    
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'hive-export_' + new Date().toISOString().split('T')[0] + '.json';
    a.click();
    URL.revokeObjectURL(url);
    
    toast('Data exported successfully', 'success');
  }).catch(() => {
    hideLoading();
    toast('Failed to export data', 'error');
  });
}

function clearData() {
  showConfirmDialog({
    title: 'Clear All Data',
    message: 'This will delete all your data including agents, conversations, and settings. This action cannot be undone.',
    confirmText: 'Clear All',
    confirmClass: 'danger',
    onConfirm: () => {
      showLoading('Clearing data...');
      
      // Delete all agents
      const agentPromises = allAgents.map(a =>
        fetch('/api/agents/' + a.id, {
          method: 'DELETE',
          headers: { 'Authorization': 'Bearer ' + T }
        })
      );
      
      // Delete all files
      const filePromises = allFiles.map(f =>
        fetch('/api/files/' + f.id, {
          method: 'DELETE',
          headers: { 'Authorization': 'Bearer ' + T }
        })
      );
      
      Promise.all([...agentPromises, ...filePromises]).then(() => {
        localStorage.clear();
        hideLoading();
        toast('All data cleared', 'success');
        setTimeout(() => location.reload(), 1000);
      }).catch(() => {
        hideLoading();
        toast('Failed to clear some data', 'error');
      });
    }
  });
}

// Theme settings
function setTheme(theme) {
  if (theme === 'dark') {
    document.documentElement.style.setProperty('--bg', '#0a0a0a');
    document.documentElement.style.setProperty('--bg2', '#141414');
    document.documentElement.style.setProperty('--bg3', '#1e1e1e');
    document.documentElement.style.setProperty('--tx', '#e4e4e4');
  } else if (theme === 'light') {
    document.documentElement.style.setProperty('--bg', '#ffffff');
    document.documentElement.style.setProperty('--bg2', '#f5f5f5');
    document.documentElement.style.setProperty('--bg3', '#e5e5e5');
    document.documentElement.style.setProperty('--tx', '#1a1a1a');
  }
  localStorage.setItem('hive_theme', theme);
  toast('Theme updated', 'success');
}

function loadTheme() {
  const theme = localStorage.getItem('hive_theme') || 'dark';
  setTheme(theme);
}
