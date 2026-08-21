/* ═══ WINDOW MANAGEMENT MODULE ═══ */

function createWindow(opts) {
  const { id, title, icon, content, width = 600, height = 500, x, y, modal = false } = opts;
  
  if (activeWindows.has(id)) {
    focusWindow(id);
    return;
  }
  
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const finalX = x !== undefined ? x : (vw - width) / 2;
  const finalY = y !== undefined ? y : (vh - height) / 2;
  
  const win = document.createElement('div');
  win.className = 'window';
  win.id = 'window-' + id;
  win.style.cssText = `left:${finalX}px;top:${finalY}px;width:${width}px;height:${height}px;z-index:${++windowZIndex}`;
  
  win.innerHTML = `
    <div class="windowHeader" onmousedown="startDragWindow(event,'${id}')">
      <div class="windowIcon">${icon || '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/></svg>'}</div>
      <div class="windowTitle">${esc(title)}</div>
      <div class="windowControls">
        <button class="windowBtn" onclick="minimizeWindow('${id}')" title="Minimize">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="5" y1="12" x2="19" y2="12"/></svg>
        </button>
        <button class="windowBtn" onclick="maximizeWindow('${id}')" title="Maximize">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/></svg>
        </button>
        <button class="windowBtn close" onclick="closeWindow('${id}')" title="Close">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </div>
    </div>
    <div class="windowBody">${content}</div>
    <div class="windowResize" onmousedown="startResizeWindow(event,'${id}')"></div>
  `;
  
  document.body.appendChild(win);
  
  activeWindows.set(id, {
    element: win,
    state: { x: finalX, y: finalY, width, height, maximized: false, minimized: false },
    modal
  });
  
  focusWindow(id);
  updateTaskbar();
  
  setTimeout(() => {
    win.style.animation = 'windowIn 0.3s var(--spring)';
  }, 10);
}

function focusWindow(id) {
  const winData = activeWindows.get(id);
  if (!winData) return;
  
  const win = winData.element;
  win.style.zIndex = ++windowZIndex;
  win.classList.add('focused');
  
  activeWindows.forEach((data, wid) => {
    if (wid !== id) data.element.classList.remove('focused');
  });
  
  if (winData.state.minimized) {
    winData.state.minimized = false;
    win.style.display = 'flex';
  }
}

function closeWindow(id) {
  const winData = activeWindows.get(id);
  if (!winData) return;
  
  const win = winData.element;
  win.style.animation = 'windowOut 0.2s var(--ease) forwards';
  
  setTimeout(() => {
    win.remove();
    activeWindows.delete(id);
    updateTaskbar();
  }, 200);
}

function minimizeWindow(id) {
  const winData = activeWindows.get(id);
  if (!winData) return;
  
  winData.state.minimized = true;
  winData.element.style.display = 'none';
  updateTaskbar();
}

function maximizeWindow(id) {
  const winData = activeWindows.get(id);
  if (!winData) return;
  
  const win = winData.element;
  const state = winData.state;
  
  if (state.maximized) {
    win.style.left = state.x + 'px';
    win.style.top = state.y + 'px';
    win.style.width = state.width + 'px';
    win.style.height = state.height + 'px';
    win.classList.remove('maximized');
    state.maximized = false;
  } else {
    state.x = parseFloat(win.style.left);
    state.y = parseFloat(win.style.top);
    state.width = win.offsetWidth;
    state.height = win.offsetHeight;
    
    win.style.left = '0';
    win.style.top = '0';
    win.style.width = '100vw';
    win.style.height = '100vh';
    win.classList.add('maximized');
    state.maximized = true;
  }
}

function startDragWindow(e, id) {
  if (e.target.closest('.windowBtn')) return;
  
  const winData = activeWindows.get(id);
  if (!winData || winData.state.maximized) return;
  
  dragWindow = id;
  const win = winData.element;
  const rect = win.getBoundingClientRect();
  
  dragOffsetX = e.clientX - rect.left;
  dragOffsetY = e.clientY - rect.top;
  
  win.classList.add('dragging');
  e.preventDefault();
}

function startResizeWindow(e, id) {
  const winData = activeWindows.get(id);
  if (!winData || winData.state.maximized) return;
  
  resizeWindow = id;
  const win = winData.element;
  
  resizeStartX = e.clientX;
  resizeStartY = e.clientY;
  resizeStartW = win.offsetWidth;
  resizeStartH = win.offsetHeight;
  
  e.preventDefault();
  e.stopPropagation();
}

document.addEventListener('mousemove', e => {
  if (dragWindow) {
    const winData = activeWindows.get(dragWindow);
    if (!winData) return;
    
    const win = winData.element;
    const newX = e.clientX - dragOffsetX;
    const newY = e.clientY - dragOffsetY;
    
    win.style.left = Math.max(0, Math.min(newX, window.innerWidth - 100)) + 'px';
    win.style.top = Math.max(0, Math.min(newY, window.innerHeight - 50)) + 'px';
  }
  
  if (resizeWindow) {
    const winData = activeWindows.get(resizeWindow);
    if (!winData) return;
    
    const win = winData.element;
    const dx = e.clientX - resizeStartX;
    const dy = e.clientY - resizeStartY;
    
    win.style.width = Math.max(320, resizeStartW + dx) + 'px';
    win.style.height = Math.max(200, resizeStartH + dy) + 'px';
  }
});

document.addEventListener('mouseup', () => {
  if (dragWindow) {
    const winData = activeWindows.get(dragWindow);
    if (winData) {
      winData.element.classList.remove('dragging');
      const rect = winData.element.getBoundingClientRect();
      winData.state.x = rect.left;
      winData.state.y = rect.top;
    }
    dragWindow = null;
  }
  
  if (resizeWindow) {
    const winData = activeWindows.get(resizeWindow);
    if (winData) {
      winData.state.width = winData.element.offsetWidth;
      winData.state.height = winData.element.offsetHeight;
    }
    resizeWindow = null;
  }
});

function updateTaskbar() {
  const taskbar = $('taskbar');
  if (!taskbar) return;
  
  if (activeWindows.size === 0) {
    taskbar.style.display = 'none';
    return;
  }
  
  taskbar.style.display = 'flex';
  taskbar.innerHTML = '';
  
  activeWindows.forEach((data, id) => {
    const win = data.element;
    const title = win.querySelector('.windowTitle')?.textContent || 'Window';
    const icon = win.querySelector('.windowIcon')?.innerHTML || '';
    const isMinimized = data.state.minimized;
    
    const btn = document.createElement('div');
    btn.className = 'taskbarItem' + (isMinimized ? ' minimized' : '');
    btn.innerHTML = `${icon}<span>${esc(title)}</span>`;
    btn.onclick = () => {
      if (isMinimized) {
        focusWindow(id);
      } else if (win.classList.contains('focused')) {
        minimizeWindow(id);
      } else {
        focusWindow(id);
      }
    };
    
    taskbar.appendChild(btn);
  });
}

// Modal windows
function showModal(id) {
  const modal = $(id);
  if (!modal) return;
  modal.style.display = 'flex';
  setTimeout(() => modal.classList.add('show'), 10);
}

function hideModal(id) {
  const modal = $(id);
  if (!modal) return;
  modal.classList.remove('show');
  setTimeout(() => modal.style.display = 'none', 200);
}

// Command palette
function openCommandPalette() {
  const modal = $('commandPalette');
  if (!modal) return;
  modal.style.display = 'flex';
  setTimeout(() => {
    modal.classList.add('show');
    const input = modal.querySelector('input');
    if (input) input.focus();
  }, 10);
}

function closeCommandPalette() {
  const modal = $('commandPalette');
  if (!modal) return;
  modal.classList.remove('show');
  setTimeout(() => modal.style.display = 'none', 200);
}

function executeCommand(cmd) {
  closeCommandPalette();
  
  const commands = {
    'chat': () => showView('chat'),
    'agents': () => showView('agents'),
    'tasks': () => showView('tasks'),
    'files': () => showView('files'),
    'dashboard': () => showView('dashboard'),
    'settings': () => showView('settings'),
    'new-room': () => showModal('mRoom'),
    'new-agent': () => showModal('mAgent'),
    'new-task': () => showModal('mTask'),
    'upload-file': () => uploadFile(),
    'logout': () => logout()
  };
  
  if (commands[cmd]) commands[cmd]();
}

// Keyboard shortcuts
document.addEventListener('keydown', e => {
  // Cmd/Ctrl + K for command palette
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
    e.preventDefault();
    openCommandPalette();
  }
  
  // Escape to close
  if (e.key === 'Escape') {
    closeCommandPalette();
    
    // Close topmost window
    if (activeWindows.size > 0) {
      const topId = Array.from(activeWindows.keys()).pop();
      closeWindow(topId);
    }
  }
  
  // Cmd/Ctrl + number for views
  if ((e.metaKey || e.ctrlKey) && e.key >= '1' && e.key <= '6') {
    e.preventDefault();
    const views = ['chat', 'agents', 'tasks', 'files', 'dashboard', 'settings'];
    const idx = parseInt(e.key) - 1;
    if (views[idx]) showView(views[idx]);
  }
});
