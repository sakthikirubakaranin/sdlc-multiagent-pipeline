'use strict';

const { contextBridge, ipcRenderer } = require('electron');

// Expose a minimal, safe API to renderer pages
contextBridge.exposeInMainWorld('sdlcApp', {
  getVersion:  () => ipcRenderer.invoke('get-version'),
  getAppRoot:  () => ipcRenderer.invoke('get-app-root'),
  onStreamlitLog: (cb) => ipcRenderer.on('streamlit-log', (_event, line) => cb(line)),
});
