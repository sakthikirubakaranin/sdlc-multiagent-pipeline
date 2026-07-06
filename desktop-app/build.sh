#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  SDLC Pipeline — macOS Desktop App Builder
#  Produces: dist/SDLC Pipeline-1.0.0-arm64.dmg  (Apple Silicon)
#            dist/SDLC Pipeline-1.0.0-x64.dmg    (Intel)
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

CYAN='\033[0;36m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
RED='\033[0;31m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
die()     { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

# ── Prerequisites ──────────────────────────────────────────────
info "Checking prerequisites…"

command -v node >/dev/null 2>&1  || die "Node.js not found. Install from https://nodejs.org (v18+)"
command -v npm  >/dev/null 2>&1  || die "npm not found. Install Node.js from https://nodejs.org"

NODE_VER=$(node -e "process.stdout.write(process.versions.node)")
info "Node.js: v${NODE_VER}"

# iconutil is macOS-only (needed for .icns)
if command -v iconutil >/dev/null 2>&1; then
  info "Building .icns icon with iconutil…"
  iconutil -c icns assets/SDLCPipeline.iconset -o assets/icons/icon.icns
  success ".icns created: assets/icons/icon.icns"
else
  warn "iconutil not found — falling back to PNG icon."
  # Patch package.json mac.icon to use the PNG instead
  if command -v node >/dev/null 2>&1; then
    node -e "
      const fs = require('fs');
      const pkg = JSON.parse(fs.readFileSync('package.json','utf8'));
      pkg.build.mac.icon = 'assets/icons/icon_512x512.png';
      fs.writeFileSync('package.json', JSON.stringify(pkg, null, 2));
    "
    info "package.json updated to use PNG icon."
  fi
fi

# Convert DMG background SVG → PNG if not already done
if [[ ! -f "assets/dmg-background.png" ]]; then
  info "Converting DMG background SVG → PNG…"
  if command -v rsvg-convert >/dev/null 2>&1; then
    rsvg-convert -w 600 -h 400 assets/dmg-background.svg -o assets/dmg-background.png
  elif command -v convert >/dev/null 2>&1; then
    convert -background none -resize 600x400 assets/dmg-background.svg assets/dmg-background.png
  elif command -v inkscape >/dev/null 2>&1; then
    inkscape --export-width=600 --export-height=400 \
             --export-filename=assets/dmg-background.png assets/dmg-background.svg 2>/dev/null
  else
    warn "No SVG converter found — DMG will use default background."
  fi
fi

# ── Install npm dependencies ───────────────────────────────────
info "Installing npm dependencies…"
npm install

# ── Build DMG ─────────────────────────────────────────────────
info "Building macOS DMG…"
echo ""

# Detect architecture
ARCH=$(uname -m)
if [[ "${ARCH}" == "arm64" ]]; then
  TARGET_ARCH="arm64"
else
  TARGET_ARCH="x64"
fi
info "Building for architecture: ${TARGET_ARCH}"

npm run build -- --${TARGET_ARCH}

echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${GREEN}║   SDLC Pipeline desktop app built successfully! 🚀   ║${NC}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BOLD}DMG location:${NC}"
ls dist/*.dmg 2>/dev/null && echo "" || warn "No .dmg found in dist/ — check build output above."
echo ""
echo -e "  ${CYAN}To install:${NC} Double-click the .dmg and drag SDLC Pipeline to Applications."
echo -e "  ${CYAN}To run dev:${NC}  cd desktop-app && npm start"
echo ""
