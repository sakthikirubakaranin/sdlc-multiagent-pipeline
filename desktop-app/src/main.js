'use strict';

const { app, BrowserWindow, Menu, shell, dialog, ipcMain, nativeTheme } = require('electron');
const { spawn, execSync } = require('child_process');
const path  = require('path');
const http  = require('http');
const fs    = require('fs');

// ── Constants ────────────────────────────────────────────────────────────────
const STREAMLIT_PORT   = 8501;
const STREAMLIT_HOST   = '127.0.0.1';
const STREAMLIT_URL    = `http://${STREAMLIT_HOST}:${STREAMLIT_PORT}`;
const POLL_INTERVAL_MS = 500;
const MAX_WAIT_MS      = 60_000;   // 60 s boot timeout
const isDev            = process.env.NODE_ENV === 'development';

// App root — works both in dev (repo root) and packaged (Resources/app)
const APP_ROOT = app.isPackaged
  ? path.join(process.resourcesPath, 'app')
  : path.join(__dirname, '..', '..');

// ── State ────────────────────────────────────────────────────────────────────
let mainWindow    = null;
let splashWindow  = null;
let streamlitProc = null;
let booting       = true;

// ── Python / venv resolution ─────────────────────────────────────────────────
function findPython() {
  const candidates = [
    path.join(APP_ROOT, '.venv', 'bin', 'python3'),
    path.join(APP_ROOT, 'venv',  'bin', 'python3'),
    '/usr/local/bin/python3',
    '/usr/bin/python3',
    'python3',
    'python',
  ];
  for (const c of candidates) {
    try {
      execSync(`"${c}" --version`, { stdio: 'ignore' });
      return c;
    } catch (_) { /* try next */ }
  }
  return 'python3';
}

// ── Launch Streamlit ─────────────────────────────────────────────────────────
function launchStreamlit() {
  const python     = findPython();
  const entryPoint = path.join(APP_ROOT, 'ui', 'app.py');

  console.log(`[SDLC] Starting Streamlit: ${python} -m streamlit run ${entryPoint}`);

  streamlitProc = spawn(python, [
    '-m', 'streamlit', 'run', entryPoint,
    '--server.port',          String(STREAMLIT_PORT),
    '--server.address',       STREAMLIT_HOST,
    '--server.headless',      'true',
    '--browser.gatherUsageStats', 'false',
    '--server.enableCORS',    'false',
    '--server.enableXsrfProtection', 'false',
  ], {
    cwd: APP_ROOT,
    env: { ...process.env, PYTHONUNBUFFERED: '1' },
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  streamlitProc.stdout.on('data', d => {
    const line = d.toString().trim();
    console.log('[Streamlit]', line);
    // Forward log lines to splash window
    if (splashWindow && !splashWindow.isDestroyed()) {
      splashWindow.webContents.send('streamlit-log', line);
    }
  });

  streamlitProc.stderr.on('data', d => {
    const line = d.toString().trim();
    if (line) console.error('[Streamlit ERR]', line);
  });

  streamlitProc.on('error', err => {
    console.error('[SDLC] Failed to start Streamlit:', err);
    dialog.showErrorBox(
      'Could not start SDLC Pipeline',
      `Failed to launch Streamlit.\n\nMake sure Python 3.10+ and Streamlit are installed:\n  pip install streamlit\n\nError: ${err.message}`
    );
    app.quit();
  });

  streamlitProc.on('exit', (code, signal) => {
    console.log(`[SDLC] Streamlit exited (code=${code}, signal=${signal})`);
    if (!booting && code !== 0 && code !== null) {
      dialog.showErrorBox('SDLC Pipeline stopped', `The pipeline server stopped unexpectedly (exit code ${code}).`);
    }
  });
}

// ── Poll until Streamlit responds ────────────────────────────────────────────
function waitForStreamlit(timeout = MAX_WAIT_MS) {
  return new Promise((resolve, reject) => {
    const start = Date.now();
    const check = () => {
      const req = http.get(STREAMLIT_URL, res => {
        res.destroy();
        resolve();
      });
      req.on('error', () => {
        if (Date.now() - start > timeout) {
          reject(new Error(`Streamlit did not start within ${timeout / 1000}s`));
        } else {
          setTimeout(check, POLL_INTERVAL_MS);
        }
      });
      req.setTimeout(1000, () => { req.destroy(); });
    };
    check();
  });
}

// ── Splash window ────────────────────────────────────────────────────────────
function createSplash() {
  splashWindow = new BrowserWindow({
    width:           480,
    height:          320,
    frame:           false,
    transparent:     false,
    resizable:       false,
    center:          true,
    alwaysOnTop:     true,
    backgroundColor: '#1e1b4b',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  });
  splashWindow.loadFile(path.join(__dirname, '..', 'splash.html'));
}

// ── Main window ──────────────────────────────────────────────────────────────
function createMainWindow() {
  mainWindow = new BrowserWindow({
    width:           1440,
    height:          900,
    minWidth:        960,
    minHeight:       600,
    show:            false,
    titleBarStyle:   'hiddenInset',
    backgroundColor: '#f8fafc',
    icon:            path.join(__dirname, '..', 'assets', 'icons', 'icon_512x512.png'),
    webPreferences: {
      nodeIntegration:  false,
      contextIsolation: true,
      preload:          path.join(__dirname, 'preload.js'),
      // Allow loading local Streamlit (localhost)
      webSecurity:      false,
    },
  });

  mainWindow.loadURL(STREAMLIT_URL);

  mainWindow.webContents.on('did-finish-load', () => {
    if (booting) {
      booting = false;
      // Fade out splash, show main
      if (splashWindow && !splashWindow.isDestroyed()) {
        splashWindow.destroy();
        splashWindow = null;
      }
      mainWindow.show();
      if (isDev) mainWindow.webContents.openDevTools();
    }
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    // Open external links in the system browser
    if (!url.startsWith(STREAMLIT_URL)) {
      shell.openExternal(url);
      return { action: 'deny' };
    }
    return { action: 'allow' };
  });

  mainWindow.on('closed', () => { mainWindow = null; });
}

// ── Application menu ─────────────────────────────────────────────────────────
function buildMenu() {
  const template = [
    {
      label: app.name,
      submenu: [
        { role: 'about' },
        { type: 'separator' },
        {
          label: 'Preferences…',
          accelerator: 'CmdOrCtrl+,',
          click: () => mainWindow?.loadURL(`${STREAMLIT_URL}/?page=%E2%9A%99%EF%B8%8F+Settings`),
        },
        { type: 'separator' },
        { role: 'hide' },
        { role: 'hideOthers' },
        { role: 'unhide' },
        { type: 'separator' },
        { role: 'quit' },
      ],
    },
    {
      label: 'Pipeline',
      submenu: [
        {
          label: 'New Run',
          accelerator: 'CmdOrCtrl+N',
          click: () => mainWindow?.loadURL(`${STREAMLIT_URL}/`),
        },
        {
          label: 'Live Status',
          accelerator: 'CmdOrCtrl+L',
          click: () => mainWindow?.loadURL(`${STREAMLIT_URL}/`),
        },
        { type: 'separator' },
        {
          label: 'Reload App',
          accelerator: 'CmdOrCtrl+R',
          click: () => mainWindow?.webContents.reload(),
        },
      ],
    },
    {
      label: 'View',
      submenu: [
        {
          label: 'Zoom In',
          accelerator: 'CmdOrCtrl+Plus',
          click: () => {
            const f = mainWindow?.webContents.getZoomFactor() ?? 1;
            mainWindow?.webContents.setZoomFactor(Math.min(f + 0.1, 2.0));
          },
        },
        {
          label: 'Zoom Out',
          accelerator: 'CmdOrCtrl+-',
          click: () => {
            const f = mainWindow?.webContents.getZoomFactor() ?? 1;
            mainWindow?.webContents.setZoomFactor(Math.max(f - 0.1, 0.5));
          },
        },
        {
          label: 'Reset Zoom',
          accelerator: 'CmdOrCtrl+0',
          click: () => mainWindow?.webContents.setZoomFactor(1.0),
        },
        { type: 'separator' },
        { role: 'togglefullscreen' },
      ],
    },
    {
      label: 'Window',
      submenu: [
        { role: 'minimize' },
        { role: 'zoom' },
        { type: 'separator' },
        { role: 'front' },
      ],
    },
    {
      label: 'Help',
      submenu: [
        {
          label: 'Open Outputs Folder',
          click: () => shell.openPath(path.join(APP_ROOT, 'outputs')),
        },
        {
          label: 'View Logs',
          click: () => shell.openPath(app.getPath('logs')),
        },
        { type: 'separator' },
        {
          label: 'Report an Issue',
          click: () => shell.openExternal('https://github.com/sdlc-pipeline/issues'),
        },
      ],
    },
  ];

  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

// ── App lifecycle ─────────────────────────────────────────────────────────────
app.whenReady().then(async () => {
  nativeTheme.themeSource = 'light';
  buildMenu();
  createSplash();
  launchStreamlit();

  try {
    await waitForStreamlit();
    createMainWindow();
  } catch (err) {
    dialog.showErrorBox('Startup Error', err.message);
    app.quit();
  }
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createMainWindow();
});

app.on('before-quit', () => {
  booting = false;
  if (streamlitProc && !streamlitProc.killed) {
    console.log('[SDLC] Stopping Streamlit…');
    streamlitProc.kill('SIGTERM');
  }
});

// IPC: renderer can request the app version
ipcMain.handle('get-version', () => app.getVersion());
ipcMain.handle('get-app-root', () => APP_ROOT);
