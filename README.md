# Apple Music Downloader Web UI

A simple web interface for the Apple Music Downloader, making it easier to download your favorite tracks with a user-friendly GUI.

## 🎵 About

This project is a web interface wrapper built around the excellent work of other developers in the Apple Music downloading community. It provides a clean, browser-based UI to interact with the powerful Apple Music Downloader tools without needing to use command-line interfaces.

**This project would not exist without the amazing work of:**
- **[zhaarey/apple-music-downloader](https://github.com/zhaarey/apple-music-downloader)** — The core Go-based Apple Music downloader that powers all the downloading functionality
- **[zhaarey/wrapper](https://github.com/zhaarey/wrapper)** — The authentication wrapper that handles Apple Music login and session management
- **[lalit22km/alac-rip](https://github.com/lalit22km/alac-rip)** — Original web UI fork that this is based on

All credit for the actual downloading capabilities goes to these original creators. This UI is simply a convenience layer on top of their excellent tools.

## ✨ Features

- **🌐 Web-based Interface**: Clean, modern web UI accessible from any browser
- **🔐 Auto-Login**: Save credentials for automatic login on startup
- **🎵 Multiple Formats**: Support for ATMOS, AAC, and standard downloads
- **📊 Real-time Logs**: Live streaming of download progress and wrapper status
- **⚙️ Settings Management**: Easy configuration of all downloader options via web interface
- **🎯 Smart Controls**: Intuitive format selection with Special Audio toggle
- **📱 Responsive Design**: Works on desktop and mobile browsers
- **🔄 Auto-retry**: Intelligent handling of failed connections and auto-login

---

## 🔀 Changes from Upstream (`lalit22km/alac-rip`)

### 🐛 Bug Fixed

**Wrapper stuck as "Stopped" after successful login (`app/routes.py`)**

The original code waited for `[.] response type 6` in the wrapper output to mark login as successful and enable the download button. The wrapper never emits that line — it ends with `[!] listening account info request on 127.0.0.1:30020` instead, so `wrapper_running` was never set to `True`.

```python
# Before (broken):
if "[.] response type 6" in line:

# After (fixed):
if "[!] listening account info request on" in line or "[.] response type 6" in line:
```

The original condition is kept as a fallback for wrapper versions that may still emit it.

---

### ✅ Added

**`DEFAULT_CONFIG` dict + `get_config_path()` + `ensure_config_exists()` (`app/routes.py`)**

The original had no fallback if `config.yaml` was missing — the settings page would crash with a file-not-found error. This fork adds:
- A full `DEFAULT_CONFIG` dict covering all known downloader options with sensible defaults
- `get_config_path()` — centralised path resolution (also creates the `apple-music-downloader/` directory if it doesn't exist yet)
- `ensure_config_exists()` — writes `DEFAULT_CONFIG` to `config.yaml` on first access if the file is absent
- `get_config` now merges the loaded config with `DEFAULT_CONFIG` so any new keys are always present even on older installs

**Robust `download_file()` helper with wget + urllib fallback (`main.py`)**

The original used a bare `urllib.request.urlretrieve()` call for both Bento4 and the wrapper, which failed silently on redirects or servers that block the default Python UA. This fork extracts a `download_file()` helper that:
- Tries `wget` first (handles redirects and sends a proper browser User-Agent)
- Falls back to `urllib` with a spoofed User-Agent if `wget` is unavailable or fails

**Wrapper binary name fallback (`main.py`)**

The original only looked for `wrapper/wrapper` (lowercase). Some releases ship the binary as `Wrapper` (capitalised). The new logic checks both, and if neither matches, `chmod`s every file in the wrapper directory as a last resort.

**Updated wrapper download URL (`main.py`)**

The original URL pointed to a specific pinned release (`Wrapper.x86_64.0df45b5`). This fork updates it to the `wrapper.x86_64.latest` release tag so setup always pulls the most recent wrapper binary.

---

### 🔧 Modified

**Config path handling (`app/routes.py`)**

All three routes that touched `config.yaml` (`get_config`, `save_config`, `get_download_folders`) previously duplicated the path-building logic inline. They now all call `get_config_path()` and `ensure_config_exists()`, removing the duplication and making config access crash-safe.

**Wrapper URL and Bento4 URL moved to module-level constants (`main.py`)**

Both URLs were previously defined as local variables inside `firstsetup()`. They are now module-level constants at the top of the file, making them easy to update in one place.

**Cleaned up verbose debug prints in `firstsetup()` (`main.py`)**

The original had redundant inline comments and repeated blank-line noise throughout `firstsetup()`. The logic is unchanged but the code is tidier.

---

## ⚠️ Known Limitations

### Credential Storage
Credentials are saved to a `.credentials` file using **base64 encoding**, which is obfuscation — not encryption. Anyone with read access to the file can decode the password instantly:
```bash
python3 -c "import base64, json; d=json.load(open('.credentials')); print(base64.b64decode(d['password']).decode())"
```
Do not use this on a shared or multi-user server. A proper fix would use the system keyring (`keyring` library) or prompt for credentials each session without saving them.

### Password Visible in Process List
The wrapper is launched as `wrapper -L email:password`, which means the plaintext password appears in `ps aux` output for the duration of the login. On a shared machine, any user can see it.

### No Input Sanitisation on Download URLs
The URL entered in the download box is passed directly to `subprocess.Popen`. `shlex` is imported but never used for sanitisation. Avoid running this exposed to untrusted users.

### In-memory Log Growth
`wrapper_logs` and `downloader_logs` are plain lists that grow unboundedly until the server restarts. The `get_logs` endpoint slices `[-200:]` at read time, but memory usage keeps climbing. A `collections.deque(maxlen=500)` would fix this.

### Thread Safety
`wrapper_running`, `download_running`, and the log lists are shared across threads with no locks. This is unlikely to cause issues in practice under Flask's GIL, but it is technically a race condition.

---

## 🚀 Quick Start

### Prerequisites

- **Linux environment** (designed for Linux, also works on WSL)
- **Root access** (the setup script must be run as root)
- **Python 3.7+** with Flask
- **Go** (for running the Apple Music Downloader)
- **Git** (for cloning repositories)

#### Important for WSL Users
This tool requires root privileges to install system packages and create symbolic links. On WSL:
1. Open your WSL terminal
2. Switch to root: `sudo -i`
3. Then run the installation commands

### Installation

1. **Clone this repository:**
   ```bash
   git clone https://github.com/Balasudhan123/alac-rip.git
   cd alac-rip
   ```

2. **Switch to root:**
   ```bash
   sudo -i
   ```

3. **Run the setup:**
   ```bash
   python3 main.py
   ```

   The first run will automatically:
   - Install required system packages
   - Download and set up Bento4
   - Download the wrapper tool
   - Clone the Apple Music Downloader
   - Install Python dependencies

4. **Access the web interface:**
   Open your browser and go to `http://localhost:5000`

---

## 📖 Usage

### First Time Setup

1. **Login**: Click "Login to Wrapper" and enter your Apple Music credentials
2. **Wait for Success**: The wrapper status will change to **Running** once login is confirmed — watch the wrapper logs for `[!] listening account info request on 127.0.0.1:30020`
3. **Configure Settings**: Click the ⚙️ Settings button to customise download preferences
4. **Start Downloading**: Paste Apple Music URLs and choose your format

### Download Options

- **Standard Download**: Uncheck "Special Audio" for basic ALAC downloads
- **ATMOS**: Check "Special Audio" and select "ATMOS" for Dolby Atmos spatial audio
- **AAC**: Check "Special Audio" and select "AAC" for AAC format

### Settings

The settings page lets you configure:
- Download folders and file naming formats
- Audio quality and format preferences
- Cover art and lyrics options
- Advanced downloader parameters

---

## ⚠️ Disclaimer

This tool is for educational purposes and personal use only. Please respect Apple's Terms of Service and only download content you have the legal right to access. The developers of this UI wrapper are not responsible for any misuse of the underlying downloading tools.

**Security Note:** This tool requires root privileges for initial setup to install system packages and configure tools. Please review the code before running with elevated privileges.

---

## 🙏 Acknowledgments

- **[@zhaarey](https://github.com/zhaarey)** for creating both the [apple-music-downloader](https://github.com/zhaarey/apple-music-downloader) and [wrapper](https://github.com/zhaarey/wrapper) projects that make this possible
- **[@lalit22km](https://github.com/lalit22km)** for the original [alac-rip](https://github.com/lalit22km/alac-rip) web UI
- The entire Apple Music downloading community for their research and tools
