'use strict';
const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('jevDesktop', Object.freeze({
  chooseDirectory: initial => ipcRenderer.invoke('jev:choose-directory', initial),
  copyText: text => ipcRenderer.invoke('jev:copy-text', text),
  status: () => ipcRenderer.invoke('jev:status'),
  retry: () => ipcRenderer.invoke('jev:retry'),
  openData: () => ipcRenderer.invoke('jev:open-data'),
  quit: () => ipcRenderer.invoke('jev:quit'),
  preferences: patch => ipcRenderer.invoke('jev:preferences', patch),
  onStatus: callback => { const handler = (_event, value) => callback(value); ipcRenderer.on('jev:status', handler); return () => ipcRenderer.removeListener('jev:status', handler); },
  onSourceSelected: callback => { const handler = (_event, value) => callback(value); ipcRenderer.on('jev:source-selected', handler); return () => ipcRenderer.removeListener('jev:source-selected', handler); }
}));
