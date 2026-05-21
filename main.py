import os
import subprocess
import urllib.request
import zipfile
from pathlib import Path
import sys

PROJECT_DIR = Path(__file__).resolve().parent
BENTO4_DIR = PROJECT_DIR / "bento4"
WRAPPER_DIR = PROJECT_DIR / "wrapper"
AMD_DIR = PROJECT_DIR / "apple-music-downloader"

# Latest URLs (updated May 2026)
BENTO4_URL = "https://www.bok.net/Bento4/binaries/Bento4-SDK-1-6-0-641.x86_64-unknown-linux.zip"
WRAPPER_URL = "https://github.com/WorldObservationLog/wrapper/releases/download/wrapper.x86_64.latest/Wrapper.x86_64.latest.zip"


def download_file(url, dest_path, label="file"):
    """Download a file robustly: tries wget first (handles redirects & UA), falls back to urllib."""
    dest_path = Path(dest_path)
    print(f"Downloading {label} from {url}...")

    # Try wget first — it handles redirects and sends a proper User-Agent
    try:
        result = subprocess.run(
            [
                "wget",
                "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                "--no-check-certificate",
                "-q",
                "--show-progress",
                "-O", str(dest_path),
                url,
            ],
            check=True,
        )
        print(f"Downloaded {label} successfully via wget.")
        return
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"wget failed ({e}), falling back to urllib...")

    # Fallback: urllib with a browser User-Agent
    opener = urllib.request.build_opener()
    opener.addheaders = [
        ("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"),
    ]
    urllib.request.install_opener(opener)
    urllib.request.urlretrieve(url, str(dest_path))
    print(f"Downloaded {label} successfully via urllib.")


def firstsetup():
    # --- Check for root ---
    if os.geteuid() != 0:
        print("ERROR: This script must be run as root. Exiting.")
        sys.exit(1)

    try:
        # Step 1: Install required packages
        subprocess.run(
            ["apt-get", "install", "-y", "git", "ffmpeg", "gpac", "golang-go", "wget",
             "python3-flask", "python3-yaml"],
            check=True
        )
        print("Packages installed successfully.")

        # Step 2: Download and set up Bento4
        zip_path = PROJECT_DIR / "bento4.zip"

        if not BENTO4_DIR.exists():
            download_file(BENTO4_URL, zip_path, label="Bento4")
            print("Extracting Bento4...")

            BENTO4_DIR.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(BENTO4_DIR)
            os.remove(zip_path)

            print("Bento4 installed inside project folder.")

            # Create symbolic links to Bento4 tools in /usr/local/bin
            bin_candidates = list(BENTO4_DIR.glob("Bento4*"))
            if bin_candidates:
                bin_dir = bin_candidates[0] / "bin"
                print(f"DEBUG: Creating symbolic links for Bento4 tools from: {bin_dir}")
                print(f"DEBUG: Bin directory exists: {bin_dir.exists()}")

                if not bin_dir.exists():
                    print(f"ERROR: Bin directory does not exist: {bin_dir}")
                    return

                all_files = list(bin_dir.glob("*"))
                print(f"DEBUG: All files in bin: {[f.name for f in all_files]}")

                # Make all files executable (ZIP extraction doesn't preserve permissions)
                print("Setting execute permissions on all Bento4 tools...")
                for exe_file in all_files:
                    if exe_file.is_file():
                        try:
                            exe_file.chmod(exe_file.stat().st_mode | 0o755)
                            print(f"  CHMOD: Set execute permission on {exe_file.name}")
                        except Exception as e:
                            print(f"  ERROR: Failed to set execute permission on {exe_file.name}: {e}")

                executable_files = [f for f in all_files if f.is_file() and os.access(f, os.X_OK)]
                print(f"DEBUG: Executable files after chmod: {[f.name for f in executable_files]}")

                os.environ["PATH"] = f"{bin_dir}:{os.environ['PATH']}"

                success_count = 0
                error_count = 0

                for exe_file in executable_files:
                    try:
                        link_path = Path("/usr/local/bin") / exe_file.name
                        if link_path.exists():
                            print(f"  INFO: Already exists: {exe_file.name}")
                        else:
                            os.symlink(str(exe_file.absolute()), str(link_path))
                            print(f"  SUCCESS: Created symlink for {exe_file.name}")
                            success_count += 1
                    except Exception as e:
                        print(f"  ERROR: Failed to create symlink for {exe_file.name}: {e}")
                        error_count += 1

                print(f"SUMMARY: {success_count} symlinks created, {error_count} errors")

                usr_local_bin = Path("/usr/local/bin")
                if usr_local_bin.exists():
                    bento4_links = [f for f in usr_local_bin.glob("*") if f.is_symlink()]
                    print(f"Found {len(bento4_links)} symlinks in /usr/local/bin")
                    for link in bento4_links:
                        if any(exe.name == link.name for exe in executable_files):
                            print(f"  VERIFIED: {link.name} -> {link.readlink()}")
            else:
                print("WARN: Could not find Bento4 extracted folder")

        else:
            print("INFO: Bento4 already exists, skipping download")

            bin_candidates = list(BENTO4_DIR.glob("Bento4*"))
            if bin_candidates:
                bin_dir = bin_candidates[0] / "bin"
                os.environ["PATH"] = f"{bin_dir}:{os.environ['PATH']}"

                try:
                    missing_links = []
                    for exe_file in bin_dir.glob("*"):
                        if exe_file.is_file() and os.access(exe_file, os.X_OK):
                            link_path = Path("/usr/local/bin") / exe_file.name
                            if not link_path.exists():
                                missing_links.append((exe_file, link_path))

                    if missing_links:
                        print("Creating missing Bento4 symbolic links...")
                        for exe_file, link_path in missing_links:
                            os.symlink(exe_file, link_path)
                            print(f"  Created symlink: {exe_file.name}")
                    else:
                        print("✅ Bento4 tools already available system-wide")

                except Exception as e:
                    print(f"WARN: Could not verify/create symbolic links: {e}")
                    print(f"Added existing Bento4 bin to current session PATH: {bin_dir}")

        # Step 3: Download and extract wrapper
        wrapper_zip = PROJECT_DIR / "wrapper.x86_64.zip"

        if not WRAPPER_DIR.exists():
            download_file(WRAPPER_URL, wrapper_zip, label="wrapper")
            print("Extracting wrapper...")

            WRAPPER_DIR.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(wrapper_zip, "r") as zip_ref:
                zip_ref.extractall(WRAPPER_DIR)
            os.remove(wrapper_zip)

            # Make the wrapper binary executable
            for candidate in [WRAPPER_DIR / "wrapper", WRAPPER_DIR / "Wrapper"]:
                if candidate.exists():
                    candidate.chmod(candidate.stat().st_mode | 0o755)
                    print(f"Set execute permission on {candidate.name}")
                    break
            else:
                # Chmod everything in the wrapper dir just in case
                for f in WRAPPER_DIR.iterdir():
                    if f.is_file():
                        try:
                            f.chmod(f.stat().st_mode | 0o755)
                        except Exception:
                            pass
                print("WARN: Wrapper binary name not detected; chmod'd all files in wrapper dir")

            print("Wrapper extracted inside project folder")
        else:
            print("INFO: Wrapper already exists, skipping download")

        # Step 4: Clone Apple Music Downloader repo
        if not AMD_DIR.exists():
            print("Cloning Apple Music Downloader...")
            subprocess.run(
                ["git", "clone", "https://github.com/zhaarey/apple-music-downloader", str(AMD_DIR)],
                check=True
            )
            print("Apple Music Downloader cloned inside project folder")
        else:
            print("INFO: Apple Music Downloader already exists, skipping clone")

        print("First setup complete!")

    except subprocess.CalledProcessError as e:
        print(f"ERROR: Failed during setup: {e}")
        sys.exit(1)


def start():
    print("Starting Apple Music Downloader Web UI...")

    bin_candidates = list(BENTO4_DIR.glob("Bento4*"))
    if bin_candidates:
        bin_dir = bin_candidates[0] / "bin"
        os.environ["PATH"] = f"{bin_dir}:{os.environ['PATH']}"

    os.environ["PATH"] = f"{WRAPPER_DIR}:{os.environ['PATH']}"

    from app import app
    app.run(host="0.0.0.0", port=5000, debug=True)


# === First run check ===
marker_file = PROJECT_DIR / "firstrun"

if not marker_file.exists():
    firstsetup()
    with open(marker_file, "w") as f:
        f.write("This file marks that first setup has been completed.\n")

start()
