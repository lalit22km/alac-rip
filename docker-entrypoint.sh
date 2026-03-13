#!/usr/bin/env bash
# =============================================================================
# docker-entrypoint.sh
# Container startup script for the Apple Music Downloader Web UI.
#
# Responsibilities:
#   1. Verify that the required tooling is in PATH.
#   2. Create a sensible default config.yaml the very first time the container
#      runs (pointing download folders at the /downloads volume).
#   3. Print a startup banner with usage notes and the legal disclaimer.
#   4. Hand control to main.py which starts the Flask web server.
# =============================================================================

set -e

# ── Colour helpers ─────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
section() { echo -e "\n${CYAN}${BOLD}==> $*${NC}"; }

# ── PATH sanity check ──────────────────────────────────────────────────────────
section "Checking toolchain"

# Verify wrapper binary
WRAPPER_BIN="/app/wrapper/wrapper"
if [ ! -x "$WRAPPER_BIN" ]; then
    # One more attempt: search under /app/wrapper for any executable
    FOUND=$(find /app/wrapper -maxdepth 2 -type f -executable | head -1)
    if [ -n "$FOUND" ]; then
        warn "Expected '$WRAPPER_BIN' but found '$FOUND'. Creating symlink."
        ln -sf "$FOUND" "$WRAPPER_BIN"
    else
        warn "Wrapper binary not found at $WRAPPER_BIN — login will fail."
    fi
else
    info "wrapper  : OK ($WRAPPER_BIN)"
fi

# Verify Bento4
BENTO4_CHECK=$(command -v mp4info 2>/dev/null || true)
if [ -z "$BENTO4_CHECK" ]; then
    # Try to find and add it dynamically
    BENTO4_BIN_DIR=$(find /app/bento4 -maxdepth 2 -type d -name "bin" | head -1)
    if [ -n "$BENTO4_BIN_DIR" ]; then
        export PATH="$BENTO4_BIN_DIR:$PATH"
        info "Bento4   : OK (added $BENTO4_BIN_DIR to PATH)"
    else
        warn "Bento4 bin directory not found — media processing may fail."
    fi
else
    info "Bento4   : OK ($BENTO4_CHECK)"
fi

# Verify Go
GO_BIN=$(command -v go 2>/dev/null || true)
if [ -z "$GO_BIN" ]; then
    warn "Go toolchain not found in PATH — downloads will not work."
else
    info "go       : OK ($(go version | awk '{print $3}'))"
fi

# Verify ffmpeg
FFMPEG_BIN=$(command -v ffmpeg 2>/dev/null || true)
if [ -z "$FFMPEG_BIN" ]; then
    warn "ffmpeg not found — audio conversion will not work."
else
    info "ffmpeg   : OK ($FFMPEG_BIN)"
fi

# ── Default config.yaml ────────────────────────────────────────────────────────
# If the /data volume is mounted (docker-compose), keep config there so it
# persists across container recreations and symlink it into the expected path.
# Fall back to writing directly in the apple-music-downloader directory.
CONFIG_FILE="/app/apple-music-downloader/config.yaml"
if [ -d "/data" ]; then
    PERSISTENT_CONFIG="/data/config.yaml"
    if [ -f "$PERSISTENT_CONFIG" ] && [ ! -f "$CONFIG_FILE" ]; then
        info "Linking persistent config from /data/config.yaml"
        ln -sf "$PERSISTENT_CONFIG" "$CONFIG_FILE"
    elif [ ! -f "$PERSISTENT_CONFIG" ] && [ -f "$CONFIG_FILE" ]; then
        info "Moving config to /data for persistence"
        mv "$CONFIG_FILE" "$PERSISTENT_CONFIG"
        ln -sf "$PERSISTENT_CONFIG" "$CONFIG_FILE"
    elif [ ! -f "$PERSISTENT_CONFIG" ] && [ ! -f "$CONFIG_FILE" ]; then
        CONFIG_FILE="$PERSISTENT_CONFIG"  # write directly to /data
    fi
fi

if [ ! -f "$CONFIG_FILE" ]; then
    section "Creating default config.yaml"
    mkdir -p "$(dirname "$CONFIG_FILE")"
    cat > "$CONFIG_FILE" << 'YAML_EOF'
# ── Authentication ────────────────────────────────────────────────────────────
# These tokens are managed automatically by the Wrapper login flow.
# You can also paste them manually here if needed.
media-user-token: ""
authorization-token: ""

# ── Regional ──────────────────────────────────────────────────────────────────
language: en-US
storefront: us

# ── Download folders (mapped to the /downloads Docker volume) ─────────────────
alac-save-folder: /downloads/alac
atmos-save-folder: /downloads/atmos
aac-save-folder: /downloads/aac

# ── Quality ───────────────────────────────────────────────────────────────────
aac-type: aac
alac-max: 192000
atmos-max: 2768
limit-max: 200

# ── Cover art ─────────────────────────────────────────────────────────────────
cover-size: 5000x5000bb
cover-format: jpg
embed-cover: true
save-artist-cover: false
save-animated-artwork: false
emby-animated-artwork: false

# ── Lyrics ────────────────────────────────────────────────────────────────────
lrc-type: lyrics
lrc-format: lrc
embed-lrc: false
save-lrc-file: false

# ── File naming ───────────────────────────────────────────────────────────────
album-folder-format: "{ArtistName}/{AlbumName}"
playlist-folder-format: "{PlaylistName}"
song-file-format: "{SongNumer}. {SongName}"
artist-folder-format: ""

# ── Tags ──────────────────────────────────────────────────────────────────────
explicit-choice: "[E]"
clean-choice: "[C]"
apple-master-choice: "[M]"
use-songinfo-for-playlist: false
dl-albumcover-for-playlist: false

# ── Conversion ────────────────────────────────────────────────────────────────
convert-after-download: false
convert-format: flac
convert-keep-original: false
convert-skip-if-source-matches: false
ffmpeg-path: ffmpeg
convert-extra-args: ""

# ── Advanced ──────────────────────────────────────────────────────────────────
max-memory-limit: 256
decrypt-m3u8-port: "127.0.0.1:10020"
get-m3u8-port: "127.0.0.1:20020"
get-m3u8-mode: hires
mv-audio-type: atmos
mv-max: 2160
get-m3u8-from-device: false
YAML_EOF
    info "Default config.yaml created at $CONFIG_FILE"
    info "You can edit settings via the web UI at http://localhost:5000/settings"
else
    info "config   : OK (found existing $CONFIG_FILE)"
fi

# ── Startup banner ─────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║        Apple Music Downloader Web UI — Docker Edition        ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  Web UI  : ${GREEN}http://localhost:5000${NC}"
echo -e "  Settings: ${GREEN}http://localhost:5000/settings${NC}"
echo ""
echo -e "  Downloads are saved to the ${CYAN}/downloads${NC} volume:"
echo -e "    ALAC  → /downloads/alac"
echo -e "    Atmos → /downloads/atmos"
echo -e "    AAC   → /downloads/aac"
echo ""
echo -e "${YELLOW}LEGAL DISCLAIMER:${NC}"
echo "  This tool is intended ONLY for accessing content you are legally"
echo "  entitled to (e.g. your own Apple Music subscription). Downloading"
echo "  copyrighted material without authorisation may violate Apple's"
echo "  Terms of Service and applicable laws. Use responsibly."
echo ""

# ── Hand off to main.py ────────────────────────────────────────────────────────
# main.py detects the 'firstrun' marker and calls start() directly,
# which sets PATH for Bento4/wrapper and launches Flask on 0.0.0.0:5000.
exec python3 /app/main.py
