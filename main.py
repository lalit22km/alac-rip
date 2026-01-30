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

def firstsetup():
    # --- Check for root ---
    if os.geteuid() != 0:
        print("ERROR: This script must be run as root. Exiting.")
        sys.exit(1)

    try:
        # Step 1: Install required packages
        subprocess.run(
            ["apt-get", "install", "-y", "git", "ffmpeg", "gpac", "golang-go", "wget","python3-flask","python3-yaml"],
            check=True
        )
        print("Packages installed successfully.")

        # Step 2: Download and set up Bento4
        BENTO4_URL = "https://www.bok.net/Bento4/binaries/Bento4-SDK-1-6-0-641.x86_64-unknown-linux.zip"
        zip_path = PROJECT_DIR / "bento4.zip"

        if not BENTO4_DIR.exists():
            print(f"Downloading Bento4 from {BENTO4_URL}...")
            urllib.request.urlretrieve(BENTO4_URL, zip_path)
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
                
                # List all files for debugging
                all_files = list(bin_dir.glob("*"))
                print(f"DEBUG: All files in bin: {[f.name for f in all_files]}")
                
                # First, make all files executable (ZIP extraction doesn't preserve execute permissions)
                print("Setting execute permissions on all Bento4 tools...")
                for exe_file in all_files:
                    if exe_file.is_file():
                        try:
                            # Add execute permission for owner, group, and others
                            current_mode = exe_file.stat().st_mode
                            new_mode = current_mode | 0o755  # rwxr-xr-x
                            exe_file.chmod(new_mode)
                            print(f"  CHMOD: Set execute permission on {exe_file.name}")
                        except Exception as e:
                            print(f"  ERROR: Failed to set execute permission on {exe_file.name}: {e}")
                
                # Now check for executable files again
                executable_files = [f for f in all_files if f.is_file() and os.access(f, os.X_OK)]
                print(f"DEBUG: Executable files after chmod: {[f.name for f in executable_files]}")
                
                # Add to current session PATH as well
                os.environ["PATH"] = f"{bin_dir}:{os.environ['PATH']}"
                
                # Create symbolic links with detailed error reporting
                success_count = 0
                error_count = 0
                
                for exe_file in executable_files:
                    try:
                        link_path = Path("/usr/local/bin") / exe_file.name
                        print(f"DEBUG: Attempting to create symlink: {exe_file.name}")
                        print(f"DEBUG: Source: {exe_file.absolute()}")
                        print(f"DEBUG: Target: {link_path}")
                        
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
                
                # Verify what actually got created
                print("Verifying /usr/local/bin contents...")
                usr_local_bin = Path("/usr/local/bin")
                if usr_local_bin.exists():
                    bento4_links = [f for f in usr_local_bin.glob("*") if f.is_symlink()]
                    print(f"Found {len(bento4_links)} symlinks in /usr/local/bin")
                    for link in bento4_links:
                        if any(exe.name == link.name for exe in executable_files):
                            print(f"  VERIFIED: {link.name} -> {link.readlink()}")
                else:
                    print("ERROR: /usr/local/bin does not exist")
            else:
                print("WARN: Could not find Bento4 extracted folder")
                
        else:
            print("INFO: Bento4 already exists, skipping download")
            
            # Ensure Bento4 tools are available even if already downloaded
            bin_candidates = list(BENTO4_DIR.glob("Bento4*"))
            if bin_candidates:
                bin_dir = bin_candidates[0] / "bin"
                os.environ["PATH"] = f"{bin_dir}:{os.environ['PATH']}"
                
                # Check if symbolic links need to be created
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
        WRAPPER_URL = "https://github.com/WorldObservationLog/wrapper/releases/download/Wrapper.x86_64.0df45b5/Wrapper.x86_64.0df45b5.zip"
        wrapper_zip = PROJECT_DIR / "wrapper.x86_64.zip"

        if not WRAPPER_DIR.exists():
            print(f"Downloading wrapper from {WRAPPER_URL}...")
            urllib.request.urlretrieve(WRAPPER_URL, wrapper_zip)
            print("Extracting wrapper...")

            WRAPPER_DIR.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(wrapper_zip, "r") as zip_ref:
                zip_ref.extractall(WRAPPER_DIR)
            os.remove(wrapper_zip)

            # Ensure the wrapper binary is executable (running as root, so no sudo needed)
            wrapper_bin = WRAPPER_DIR / "wrapper"
            try:
                if wrapper_bin.exists():
                    current_mode = wrapper_bin.stat().st_mode
                    wrapper_bin.chmod(current_mode | 0o755)
                    print("Set execute permission on wrapper binary")
                else:
                    print("WARN: Wrapper binary not found after extraction")
            except Exception as e:
                print(f"WARN: Failed to chmod wrapper binary: {e}")

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
            
            # Fix Go version format in go.mod (e.g., change "go 1.23.1" to "go 1.23")
            go_mod_path = AMD_DIR / "go.mod"
            if go_mod_path.exists():
                try:
                    with open(go_mod_path, 'r') as f:
                        content = f.read()
                    
                    # Replace 3-part version numbers with 2-part format
                    import re
                    fixed_content = re.sub(r'^go (\d+\.\d+)\.\d+', r'go \1', content, flags=re.MULTILINE)
                    
                    if fixed_content != content:
                        with open(go_mod_path, 'w') as f:
                            f.write(fixed_content)
                        print("Fixed Go version format in go.mod")
                except Exception as e:
                    print(f"WARN: Could not fix go.mod: {e}")
        else:
            print("INFO: Apple Music Downloader already exists, skipping clone")

        print("First setup complete!")

    except subprocess.CalledProcessError as e:
        print(f"ERROR: Failed during setup: {e}")
        sys.exit(1)

def start():
    print("Starting Apple Music Downloader Web UI...")

    # Ensure Bento4 and Wrapper are in PATH locally
    bin_candidates = list(BENTO4_DIR.glob("Bento4*"))  # find extracted folder
    if bin_candidates:
        bin_dir = bin_candidates[0] / "bin"
        os.environ["PATH"] = f"{bin_dir}:{os.environ['PATH']}"

    os.environ["PATH"] = f"{WRAPPER_DIR}:{os.environ['PATH']}"

    # Import and run the Flask app
    from app import app   # FIXED: no double "app.app"
    app.run(host="0.0.0.0", port=5000, debug=True)

# === First run check ===
marker_file = PROJECT_DIR / "firstrun"

if not marker_file.exists():
    firstsetup()
    with open(marker_file, "w") as f:
        f.write("This file marks that first setup has been completed.\n")

start()
