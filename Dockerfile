# =============================================================================
# Apple Music Downloader Web UI — Docker Image
# =============================================================================
# Builds a self-contained Linux container that runs the Flask web UI and all
# required tooling (Go downloader, Bento4, Wrapper) without any host-side
# root access beyond Docker itself.
#
# Build :  docker build -t alac-rip .
# Run   :  docker run -p 5000:5000 -v "$(pwd)/downloads:/downloads" alac-rip
# =============================================================================

FROM ubuntu:22.04

# ── Environment ────────────────────────────────────────────────────────────────
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    GOPATH=/root/go \
    # Pre-set Bento4 bin + wrapper dirs in PATH so they are available even
    # before main.py's start() function patches os.environ["PATH"].
    PATH="/app/bento4/Bento4-SDK-1-6-0-641.x86_64-unknown-linux/bin:/app/wrapper:/root/go/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

WORKDIR /app

# ── System packages ────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        ffmpeg \
        gpac \
        golang-go \
        wget \
        unzip \
        python3 \
        python3-pip \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ── Python dependencies ────────────────────────────────────────────────────────
RUN pip3 install --no-cache-dir flask pyyaml

# ── Application source ─────────────────────────────────────────────────────────
# Copy the repo first so that COPY layers are cached before the slow network
# download steps that follow.
COPY . /app/

# ── Bento4 SDK ─────────────────────────────────────────────────────────────────
# Downloaded to /app/bento4/ which is exactly where main.py expects it
# (PROJECT_DIR / "bento4").
RUN mkdir -p /app/bento4 \
    && wget -q \
        "https://www.bok.net/Bento4/binaries/Bento4-SDK-1-6-0-641.x86_64-unknown-linux.zip" \
        -O /tmp/bento4.zip \
    && unzip -q /tmp/bento4.zip -d /app/bento4 \
    && rm /tmp/bento4.zip \
    # Make every file in the extracted bin/ directory executable.
    && find /app/bento4 -path "*/bin/*" -type f -exec chmod 755 {} \;

# ── Wrapper binary ─────────────────────────────────────────────────────────────
# The release zip may name the binary "Wrapper" (capital W); routes.py expects
# the path  <project>/wrapper/wrapper  (lowercase w), so we create a symlink
# when necessary.
RUN mkdir -p /app/wrapper \
    && wget -q \
        "https://github.com/WorldObservationLog/wrapper/releases/download/Wrapper.x86_64.0df45b5/Wrapper.x86_64.0df45b5.zip" \
        -O /tmp/wrapper.zip \
    && unzip -q /tmp/wrapper.zip -d /app/wrapper \
    && rm /tmp/wrapper.zip \
    # Make all extracted files executable.
    && find /app/wrapper -type f -exec chmod 755 {} \; \
    # Normalise binary name to lowercase "wrapper" if needed.
    && if [ ! -f /app/wrapper/wrapper ] && [ -f /app/wrapper/Wrapper ]; then \
           ln -s /app/wrapper/Wrapper /app/wrapper/wrapper; \
       fi

# ── Apple Music Downloader (Go) ────────────────────────────────────────────────
RUN git clone --depth 1 \
        https://github.com/zhaarey/apple-music-downloader \
        /app/apple-music-downloader

# Pre-download Go module dependencies so the first `go run` is faster.
RUN cd /app/apple-music-downloader \
    && go mod download 2>/dev/null || echo "[docker-build] go mod download skipped — will run at first use"

# ── First-run marker ───────────────────────────────────────────────────────────
# main.py skips the firstsetup() function when this file is present, because
# all setup has already been performed by the Dockerfile above.
RUN touch /app/firstrun

# ── Downloads directory ────────────────────────────────────────────────────────
# Default download target; mount a host directory here to persist files.
RUN mkdir -p /downloads/alac /downloads/atmos /downloads/aac

# ── Entrypoint ─────────────────────────────────────────────────────────────────
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 5000

# Declare the downloads directory as a named volume so users can easily
# mount it: -v my_downloads:/downloads
VOLUME ["/downloads"]

ENTRYPOINT ["/docker-entrypoint.sh"]
