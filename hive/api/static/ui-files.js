/* ═══ FILES MODULE ═══ */

function loadFiles() {
  api('/api/files').then(f => {
    allFiles = f;
    $('fileCount').textContent = f.length;
    const totalSize = f.reduce((sum, file) => sum + (file.size || 0), 0);
    $('fileSize').textContent = (totalSize / (1024 * 1024)).toFixed(2) + ' MB';
    
    if (!f.length) {
      $('fileGrid').innerHTML = '<div class="emptyState"><div class="emptyStateIcon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><polyline points="13 2 13 9 20 9"/></svg></div><div class="emptyStateTitle">No files uploaded</div><div class="emptyStateDesc">Upload files to use them with your agents</div></div>';
      return;
    }
    
    $('fileGrid').innerHTML = f.map(x => {
      const icon = getFileIcon(x.name);
      const size = formatFileSize(x.size || 0);
      const date = x.created_at ? fmtTime(x.created_at) : 'Unknown';
      return `<div class="fileCard" onclick="viewFile('${x.id}','${esc(x.name)}')">
        <div class="fileActions">
          <button class="fileAction" onclick="event.stopPropagation();downloadFile('${x.id}','${esc(x.name)}')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            <span>Download</span>
          </button>
          <button class="fileAction" onclick="event.stopPropagation();deleteFile('${x.id}','${esc(x.name)}')" style="color:var(--rd)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
            <span>Delete</span>
          </button>
        </div>
        <div class="fileIcon">${icon}</div>
        <div class="fileName">${esc(x.name)}</div>
        <div class="fileMeta">
          <span>${size}</span>
          <span>${date}</span>
        </div>
      </div>`;
    }).join('');
  });
}

function getFileIcon(filename) {
  const ext = filename.split('.').pop().toLowerCase();
  const icons = {
    pdf: '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>',
    doc: '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>',
    docx: '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>',
    txt: '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>',
    jpg: '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>',
    jpeg: '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>',
    png: '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>',
    gif: '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>',
    mp3: '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>',
    mp4: '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2"/></svg>',
    zip: '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 8v13H3V8"/><path d="M1 3h22v5H1z"/><path d="M10 12h4"/></svg>',
    csv: '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>',
    json: '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>'
  };
  return icons[ext] || '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><polyline points="13 2 13 9 20 9"/></svg>';
}

function formatFileSize(bytes) {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

function uploadFile() {
  const input = document.createElement('input');
  input.type = 'file';
  input.multiple = true;
  input.onchange = e => {
    const files = Array.from(e.target.files);
    if (!files.length) return;
    
    files.forEach(file => {
      const formData = new FormData();
      formData.append('file', file);
      
      showLoading('Uploading ' + file.name + '...');
      fetch('/api/files?user_id=' + U, {
        method: 'POST',
        headers: { 'Authorization': 'Bearer ' + T },
        body: formData
      }).then(r => {
        if (!r.ok) throw new Error();
        return r.json();
      }).then(() => {
        hideLoading();
        loadFiles();
        toast('Uploaded ' + file.name, 'success');
      }).catch(() => {
        hideLoading();
        toast('Failed to upload ' + file.name, 'error');
      });
    });
  };
  input.click();
}

function downloadFile(id, name) {
  const link = document.createElement('a');
  link.href = '/api/files/' + id + '/download?user_id=' + U;
  link.download = name;
  link.style.display = 'none';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  toast('Downloading ' + name, 'info');
}

function deleteFile(id, name) {
  showConfirmDialog({
    title: 'Delete File',
    message: `Are you sure you want to delete "${name}"? This action cannot be undone.`,
    confirmText: 'Delete',
    confirmClass: 'danger',
    onConfirm: () => {
      fetch('/api/files/' + id, {
        method: 'DELETE',
        headers: { 'Authorization': 'Bearer ' + T }
      }).then(r => {
        if (!r.ok) throw new Error();
        return r.json();
      }).then(() => {
        loadFiles();
        toast('Deleted ' + name, 'success');
      }).catch(() => toast('Failed to delete', 'error'));
    }
  });
}

function viewFile(id, name) {
  const file = allFiles.find(f => f.id === id);
  if (!file) return;
  
  const icon = getFileIcon(name);
  const size = formatFileSize(file.size || 0);
  const date = file.created_at ? fmtTime(file.created_at) : 'Unknown';
  
  const content = `
    <div style="text-align:center;padding:20px 0">
      <div style="width:80px;height:80px;margin:0 auto 16px;display:flex;align-items:center;justify-content:center;background:var(--bg4);border:1px solid var(--bd);border-radius:var(--r16);color:var(--ac)">${icon}</div>
      <div style="font-size:18px;font-weight:700;margin-bottom:8px">${esc(name)}</div>
      <div style="display:flex;gap:16px;justify-content:center;color:var(--tx3);font-size:13px">
        <span>${size}</span>
        <span>${date}</span>
      </div>
    </div>
    
    <div style="display:flex;gap:8px;margin-top:20px">
      <button class="btn btnP" onclick="downloadFile('${id}','${esc(name)}')">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
        Download
      </button>
      <button class="btn btnD" onclick="deleteFile('${id}','${esc(name)}');closeWindow('file-${id}')">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
        Delete
      </button>
      <button class="btn btnS" onclick="closeWindow('file-${id}')" style="margin-left:auto">Close</button>
    </div>
  `;
  
  const vw = window.innerWidth, vh = window.innerHeight;
  createWindow({
    id: 'file-' + id,
    title: name,
    icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><polyline points="13 2 13 9 20 9"/></svg>',
    content: content,
    width: 500,
    height: 400,
    x: (vw - 500) / 2,
    y: (vh - 400) / 2
  });
}

// Drag and drop
function initFileDrop() {
  const dropZone = $('fileDropZone');
  if (!dropZone) return;
  
  ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(event => {
    dropZone.addEventListener(event, e => {
      e.preventDefault();
      e.stopPropagation();
    });
  });
  
  ['dragenter', 'dragover'].forEach(event => {
    dropZone.addEventListener(event, () => {
      dropZone.classList.add('dragover');
    });
  });
  
  ['dragleave', 'drop'].forEach(event => {
    dropZone.addEventListener(event, () => {
      dropZone.classList.remove('dragover');
    });
  });
  
  dropZone.addEventListener('drop', e => {
    const files = Array.from(e.dataTransfer.files);
    if (!files.length) return;
    
    files.forEach(file => {
      const formData = new FormData();
      formData.append('file', file);
      
      showLoading('Uploading ' + file.name + '...');
      fetch('/api/files?user_id=' + U, {
        method: 'POST',
        headers: { 'Authorization': 'Bearer ' + T },
        body: formData
      }).then(r => {
        if (!r.ok) throw new Error();
        return r.json();
      }).then(() => {
        hideLoading();
        loadFiles();
        toast('Uploaded ' + file.name, 'success');
      }).catch(() => {
        hideLoading();
        toast('Failed to upload ' + file.name, 'error');
      });
    });
  });
}
