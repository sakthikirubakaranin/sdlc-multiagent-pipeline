# SDLC Pipeline — Desktop App

A native macOS wrapper for the SDLC Agent Pipeline. Launches the Streamlit UI inside
a proper macOS window with a custom dock icon, splash screen, and native menu bar.

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Node.js | 18+ | https://nodejs.org |
| npm | 9+ | bundled with Node |
| Python | 3.10+ | system or `pyenv` |
| Streamlit | latest | `pip install streamlit` |

## Build the DMG

```bash
cd desktop-app
chmod +x build.sh
./build.sh
```

The DMG will appear in `desktop-app/dist/`.

## Run in Development Mode

```bash
cd desktop-app
npm install
npm start          # or: npm run dev  (opens DevTools)
```

## App Structure

```
desktop-app/
├── assets/
│   ├── icon.svg               ← master icon source
│   ├── icons/                 ← PNG sizes (16–1024px)
│   ├── SDLCPipeline.iconset/  ← macOS iconset (→ iconutil → .icns)
│   ├── dmg-background.svg     ← DMG installer background
│   └── dmg-background.png     ← rendered background
├── src/
│   ├── main.js                ← Electron main process
│   └── preload.js             ← context-isolated bridge
├── splash.html                ← loading screen (shown while Streamlit boots)
├── package.json               ← electron-builder config + npm scripts
├── build.sh                   ← one-command build script
└── README.md
```

## How it Works

1. Electron starts and shows the **splash screen**
2. Streamlit is launched as a background child process (`python -m streamlit run ui/app.py`)
3. Electron polls `http://127.0.0.1:8501` until Streamlit responds
4. The splash fades out and the main window loads the Streamlit UI
5. On quit, Streamlit is terminated cleanly

## Troubleshooting

**"Could not start SDLC Pipeline" dialog**
— Make sure Python and Streamlit are installed and available on `PATH`.

**App opens but shows blank page**
— Streamlit may still be booting. Wait a few seconds and press `Cmd+R` to reload.

**Build fails with code signing error**
— The build config disables code signing for local development.
  For distribution you'll need an Apple Developer certificate.

**Changing the app icon**
— Edit `assets/icon.svg`, re-run `build.sh`. The script auto-generates all PNG sizes.
