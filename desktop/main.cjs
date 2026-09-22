'use strict';
const { app, BrowserWindow, Menu, dialog, ipcMain, protocol, session, shell, clipboard, screen } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawn } = require('node:child_process');
const { portablePaths, sameOrigin, isLauncher, readiness } = require('./lifecycle.cjs');

protocol.registerSchemesAsPrivileged([{ scheme: 'jev-app', privileges: { standard: true, secure: true, supportFetchAPI: true } }]);
app.setName('JEV');
app.commandLine.appendSwitch('disable-background-networking');
const paths = portablePaths({ executable: process.execPath, portableDir: process.env.PORTABLE_EXECUTABLE_DIR, packaged: app.isPackaged, projectDir: __dirname });
let setupError;
try {
  for (const dir of [paths.data, paths.source, path.join(paths.data, 'desktop'), path.join(paths.data, 'logs')]) fs.mkdirSync(dir, { recursive: true });
  fs.accessSync(paths.data, fs.constants.W_OK);
  app.setPath('userData', path.join(paths.data, 'desktop'));
  app.setPath('sessionData', path.join(paths.data, 'desktop', 'chromium'));
  app.setPath('crashDumps', path.join(paths.data, 'logs', 'crashes'));
} catch (error) { setupError = error; }
const locked = app.requestSingleInstanceLock();
if (!locked) app.quit();

let window, child, origin = '', token = '', starting = false, quitting = false, allowQuit = false;
let launchState = { state: 'starting', message: '正在检查本地运行环境…', dataPath: paths.data };
const logPath = path.join(paths.data, 'logs', 'desktop.log');
function log(message) {
  try {
    if (fs.existsSync(logPath) && fs.statSync(logPath).size > 4 * 1024 * 1024) fs.renameSync(logPath, logPath + '.previous');
    fs.appendFileSync(logPath, new Date().toISOString() + ' ' + String(message).replaceAll(token || '\0', '[redacted]') + '\n');
  } catch { /* A startup failure still needs its visible error screen. */ }
}
function status(state, message) {
  launchState = { state, message, dataPath: paths.data };
  if (window && !window.isDestroyed()) window.webContents.send('jev:status', launchState);
  log(state + ': ' + message);
}
function authorize(event, launcherOnly = false) {
  if (!window || event.sender !== window.webContents || event.senderFrame !== window.webContents.mainFrame) throw new Error('Unknown IPC sender');
  const url = event.senderFrame.url;
  if (!(isLauncher(url) || (!launcherOnly && sameOrigin(url, origin)))) throw new Error('Untrusted IPC origin');
}
async function chooseDirectory(initial) {
  const result = await dialog.showOpenDialog(window, { title: '选择 JEV 文档目录', defaultPath: typeof initial === 'string' && initial.length < 2000 ? initial : paths.source, properties: ['openDirectory', 'dontAddToRecent'], buttonLabel: '选择此目录' });
  return { cancelled: result.canceled, path: result.filePaths[0] || null };
}
function registerIPC() {
  ipcMain.handle('jev:choose-directory', (event, initial) => { authorize(event); return chooseDirectory(initial); });
  ipcMain.handle('jev:copy-text', (event, text) => { authorize(event); if (typeof text !== 'string' || text.length > 100000) throw new Error('Invalid clipboard value'); clipboard.writeText(text); });
  ipcMain.handle('jev:status', event => { authorize(event); return launchState; });
  ipcMain.handle('jev:open-data', event => { authorize(event); return shell.openPath(path.join(paths.data, 'logs')); });
  ipcMain.handle('jev:retry', event => { authorize(event, true); if (!starting) void startBackend(); });
  ipcMain.handle('jev:quit', event => { authorize(event); app.quit(); });
  ipcMain.handle('jev:preferences', (event, patch) => {
    authorize(event);
    const file = path.join(paths.data, 'preferences.json');
    let value = { topK: 12, maxEvidence: 3 };
    try { const saved = JSON.parse(fs.readFileSync(file, 'utf8')); if ([4,8,12,20,30].includes(saved.topK)) value.topK = saved.topK; if ([1,2,3,4,6].includes(saved.maxEvidence)) value.maxEvidence = saved.maxEvidence; } catch { /* Defaults for a new portable directory. */ }
    if (patch !== undefined) {
      if (!patch || typeof patch !== 'object') throw new Error('Invalid preferences');
      if ('topK' in patch) { if (![4,8,12,20,30].includes(patch.topK)) throw new Error('Invalid candidate count'); value.topK = patch.topK; }
      if ('maxEvidence' in patch) { if (![1,2,3,4,6].includes(patch.maxEvidence)) throw new Error('Invalid evidence count'); value.maxEvidence = patch.maxEvidence; }
      fs.writeFileSync(file + '.pending', JSON.stringify(value)); fs.renameSync(file + '.pending', file);
    }
    return value;
  });
}
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function request(route, options = {}) {
  return fetch(origin + route, { ...options, headers: { 'X-JEV-Desktop-Token': token, ...options.headers }, signal: AbortSignal.timeout(2500) });
}
async function stopBackend() {
  const processToStop = child;
  if (!processToStop) return;
  child = null;
  if (origin && processToStop.exitCode === null) {
    try { await request('/api/desktop/shutdown', { method: 'POST' }); } catch { /* May already be stopped. */ }
  }
  for (let i = 0; i < 30 && processToStop.exitCode === null && !processToStop.killed; i++) await delay(100);
  if (processToStop.exitCode === null && !processToStop.killed) processToStop.kill();
  origin = '';
}
async function showFailure(error) {
  if (quitting) return;
  log(error?.stack || error);
  status('failed', String(error.message || error));
  if (window && !window.isDestroyed()) {
    await window.loadURL('jev-app://desktop/launch.html');
    window.show();
  }
}
async function startBackend() {
  if (starting || quitting) return;
  starting = true;
  try {
    await stopBackend();
    status('starting', '正在检查本地模型和运行环境…');
    const backendDir = app.isPackaged ? path.join(paths.root, 'JEV-runtime') : path.join(__dirname, 'build', 'backend');
    const python = path.join(backendDir, 'python', 'python.exe');
    const required = ['nanojev/best.safetensors', 'nanojev/config.json', 'nanojev/backbone_config/config.json', 'nanojev/tokenizer/tokenizer.json', 'nanojev/tokenizer/tokenizer_config.json', 'ocr/det.onnx', 'ocr/cls.onnx', 'ocr/rec.onnx'];
    if (!fs.existsSync(python)) throw new Error('运行环境不完整。请重新解压完整的 JEV 便携包。\n开发环境请先运行 prepare-runtime。');
    const missing = required.filter(name => !fs.existsSync(path.join(paths.models, name)));
    if (missing.length) throw new Error('本地模型不完整。请将便携包中的 JEV-models 文件夹与 EXE 放在同一目录。\n缺少：' + missing.join('、'));
    token = crypto.randomBytes(32).toString('hex');
    status('starting', '正在启动本地检索服务…');
    const env = { ...process.env, JEV_DESKTOP_TOKEN: token, JEV_PARENT_PID: String(process.pid), JEV_STORAGE_DIR: path.join(paths.data, 'storage'), JEV_SOURCE_ROOT: paths.source, JEV_MODELS_DIR: paths.models, NANOJEV_CHECKPOINT_DIR: path.join(paths.models, 'nanojev'), NANOJEV_DEVICE: 'cpu', NANOJEV_PRECISION: 'fp32', HF_HUB_OFFLINE: '1', TRANSFORMERS_OFFLINE: '1', HF_HUB_DISABLE_TELEMETRY: '1', PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8', PYTHONDONTWRITEBYTECODE: '1', TOKENIZERS_PARALLELISM: 'false' };
    delete env.PYTHONHOME; delete env.PYTHONPATH;
    const backend = spawn(python, ['-I', '-B', '-X', 'utf8', '-u', path.join(backendDir, 'backend_entry.py')], { cwd: backendDir, env, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
    child = backend;
    let stderrTail = '';
    backend.stderr.on('data', data => { const value = data.toString('utf8'); stderrTail = (stderrTail + value).slice(-5000); log(value); });
    await new Promise((resolve, reject) => {
      let buffer = '', settled = false;
      const timer = setTimeout(() => { settled = true; reject(new Error('本地服务启动超时，请查看日志后重试。')); }, 90000);
      backend.on('error', error => { clearTimeout(timer); settled = true; reject(error); });
      backend.on('exit', (code, signal) => {
        clearTimeout(timer);
        log(`backend exited code=${code} signal=${signal}`);
        if (!settled) { settled = true; reject(new Error('本地服务无法启动。\n' + stderrTail.slice(-1500))); }
        else if (child === backend && !quitting && !starting) { child = null; origin = ''; void showFailure(new Error('本地服务意外退出。你的已完成索引仍然保留，可重新启动。\n' + stderrTail.slice(-1000))); }
      });
      backend.stdout.on('data', data => {
        buffer += data.toString('utf8');
        let end;
        while ((end = buffer.indexOf('\n')) >= 0) {
          const line = buffer.slice(0, end).trim(); buffer = buffer.slice(end + 1);
          if (!settled) {
            try { const ready = readiness(line); if (ready) { if (ready.pid !== backend.pid) throw new Error('Backend process identity mismatch'); origin = `http://127.0.0.1:${ready.port}`; clearTimeout(timer); settled = true; resolve(); } }
            catch (error) { clearTimeout(timer); settled = true; reject(error); }
          }
          log(line);
        }
      });
    });
    let healthy = false, configuration;
    for (let i = 0; i < 80 && !quitting && backend.exitCode === null; i++) {
      try { const response = await request('/api/health'); const body = await response.json(); if (response.ok && body.service === 'JEV' && body.version === app.getVersion()) { healthy = true; configuration = body; break; } } catch { /* Wait until ASGI startup is complete. */ }
      await delay(200);
    }
    if (quitting) return;
    if (!healthy) throw new Error('本地服务未通过启动检查，请打开日志查看原因。');
    if (configuration.needs_reindex && configuration.source_root.is_default) await request('/api/index/rebuild', { method: 'POST' });
    status('ready', '本地服务已就绪');
    await window.loadURL(origin + '/');
    window.show();
    // Test tooling can discover the port, never the authentication secret.
    fs.writeFileSync(path.join(paths.data, 'desktop-session.json'), JSON.stringify({ pid: process.pid, backendPid: backend.pid, origin, startedAt: new Date().toISOString() }, null, 2));
  } catch (error) {
    await stopBackend();
    await showFailure(error);
  } finally { starting = false; }
}
function createWindow() {
  let bounds = { width: 1400, height: 900 };
  try { const saved = JSON.parse(fs.readFileSync(path.join(paths.data, 'window.json'), 'utf8')); if (Number.isInteger(saved.width) && Number.isInteger(saved.height)) bounds = { width: Math.max(900, Math.min(saved.width, 2400)), height: Math.max(650, Math.min(saved.height, 1600)) }; } catch { /* First launch. */ }
  const area = screen.getPrimaryDisplay().workAreaSize;
  bounds.width = Math.min(bounds.width, area.width); bounds.height = Math.min(bounds.height, area.height);
  window = new BrowserWindow({ ...bounds, minWidth: 860, minHeight: 620, title: 'JEV · 本地文档检索', backgroundColor: '#f5f7fa', show: false, icon: path.join(__dirname, 'assets', 'icon.png'), webPreferences: { preload: path.join(__dirname, 'preload.cjs'), contextIsolation: true, sandbox: true, nodeIntegration: false, webSecurity: true, spellcheck: false, devTools: !app.isPackaged } });
  window.once('ready-to-show', () => window.show());
  window.on('close', () => { try { fs.writeFileSync(path.join(paths.data, 'window.json'), JSON.stringify(window.getNormalBounds())); } catch { /* Nonessential UI preference. */ } });
  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  window.webContents.on('will-navigate', (event, url) => { if (!(sameOrigin(url, origin) || isLauncher(url))) event.preventDefault(); });
  window.webContents.on('will-attach-webview', event => event.preventDefault());
  window.webContents.on('render-process-gone', (_event, detail) => { if (!quitting) void showFailure(new Error('页面进程退出，可重新启动。' + detail.reason)); });
  const ses = session.defaultSession;
  ses.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
  ses.setPermissionCheckHandler(() => false);
  ses.webRequest.onBeforeRequest((details, callback) => callback({ cancel: !(sameOrigin(details.url, origin) || details.url.startsWith('jev-app://desktop/')) }));
  ses.webRequest.onBeforeSendHeaders((details, callback) => {
    const headers = { ...details.requestHeaders };
    if (sameOrigin(details.url, origin)) headers['X-JEV-Desktop-Token'] = token;
    callback({ requestHeaders: headers });
  });
  ses.webRequest.onHeadersReceived((details, callback) => {
    const headers = { ...details.responseHeaders };
    headers['Content-Security-Policy'] = ["default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"];
    callback({ responseHeaders: headers });
  });
  ses.on('will-download', async (event, item) => {
    if (!sameOrigin(item.getURL(), origin) || !new URL(item.getURL()).pathname.match(/^\/api\/documents\/[a-f0-9]+\/raw$/)) { event.preventDefault(); return; }
    // Chromium's native save dialog handles overwrite confirmation.
    item.setSaveDialogOptions({ title: '保存原始文档', defaultPath: path.join(app.getPath('downloads'), path.basename(item.getFilename())) });
  });
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    { label: '文件', submenu: [
      { label: '选择文档目录…', accelerator: 'CmdOrCtrl+O', click: async () => { if (!origin) return; const selected = await chooseDirectory(paths.source); if (!selected.cancelled) window.webContents.send('jev:source-selected', selected.path); } },
      { label: '打开默认 JEV 文件夹', click: () => shell.openPath(paths.source) },
      { label: '打开数据与日志目录', click: () => shell.openPath(paths.data) },
      { type: 'separator' }, { label: '退出 JEV', accelerator: 'CmdOrCtrl+Q', click: () => app.quit() }
    ]},
    { label: '编辑', submenu: [{ role: 'undo', label: '撤销' }, { role: 'redo', label: '重做' }, { type: 'separator' }, { role: 'cut', label: '剪切' }, { role: 'copy', label: '复制' }, { role: 'paste', label: '粘贴' }, { role: 'selectAll', label: '全选' }] },
    { label: '视图', submenu: [{ role: 'reload', label: '重新加载页面' }, { role: 'resetZoom', label: '实际大小' }, { role: 'zoomIn', label: '放大' }, { role: 'zoomOut', label: '缩小' }, { role: 'togglefullscreen', label: '全屏' }] },
    { label: '帮助', submenu: [{ label: '关于 JEV', click: () => dialog.showMessageBox(window, { type: 'info', title: '关于 JEV', message: `JEV ${app.getVersion()} · Windows 便携版`, detail: '本地 NanoJev + 原文证据检索\nCPU FP32 · 完全离线运行\n模型目录：' + paths.models + '\n数据目录：' + paths.data + '\n\n公开模型以游戏决策为训练目标，文档检索质量仍需按实际资料验证。' }) }] }
  ]));
  void window.loadURL('jev-app://desktop/launch.html');
}
app.on('second-instance', () => { if (window) { if (window.isMinimized()) window.restore(); window.show(); window.focus(); } });
app.on('window-all-closed', () => app.quit());
app.on('before-quit', event => {
  if (allowQuit) return;
  event.preventDefault();
  if (quitting) return;
  quitting = true;
  void stopBackend().finally(() => {
    try { fs.unlinkSync(path.join(paths.data, 'desktop-session.json')); } catch { /* Only our ephemeral session marker. */ }
    allowQuit = true; app.quit();
  });
});
if (locked) app.whenReady().then(async () => {
  if (setupError) { dialog.showErrorBox('JEV 无法写入数据目录', '请将完整便携包放在当前用户可写的目录。\n' + String(setupError)); allowQuit = true; app.quit(); return; }
  protocol.handle('jev-app', request => {
    const url = new URL(request.url);
    const files = { '/launch.html': 'text/html; charset=utf-8', '/launch.css': 'text/css; charset=utf-8', '/launch.js': 'text/javascript; charset=utf-8' };
    if (url.hostname !== 'desktop' || !files[url.pathname]) return new Response('Not found', { status: 404 });
    return new Response(fs.readFileSync(path.join(__dirname, 'renderer', url.pathname.slice(1))), { headers: { 'Content-Type': files[url.pathname] } });
  });
  app.setAppUserModelId('local.jev.desktop');
  registerIPC(); createWindow(); await startBackend();
}).catch(error => { log(error.stack); dialog.showErrorBox('JEV 启动失败', String(error)); app.quit(); });
