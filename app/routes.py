import subprocess
import threading
from flask import render_template, request, jsonify
import shlex
import yaml
import os
import json
import base64
from . import app

wrapper_process = None
wrapper_running = False
wrapper_needs_2fa = False
download_process = None
download_running = False

def stream_download_logs(pipe, target_list):
    """Thread target to read logs from download process and store them."""
    global download_running, download_process
    
    try:
        for line in iter(pipe.readline, ''):
            line = line.strip()
            if line:
                target_list.append(line)
                print(f"[DOWNLOAD LOG] {line}")  # Debug print
                    
    except Exception as e:
        target_list.append(f"Error reading download logs: {str(e)}")
    finally:
        # Check if process ended
        if download_process and download_process.poll() is not None:
            exit_code = download_process.poll()
            if exit_code == 0:
                target_list.append("Download completed successfully.")
            else:
                target_list.append(f"Download failed with exit code: {exit_code}")
            download_running = False
        pipe.close()

def stream_wrapper_logs(pipe, target_list, email=None, password=None, auto_login=False):
    """Thread target to read logs from wrapper process and store them."""
    global wrapper_running, wrapper_process, wrapper_needs_2fa
    login_successful = False
    
    try:
        for line in iter(pipe.readline, ''):
            line = line.strip()
            if line:
                target_list.append(line)
                print(f"[WRAPPER LOG] {line}")  # Debug print
                
                # Check for 2FA requirement
                if "credentialHandler:" in line and "2FA: true" in line:
                    wrapper_needs_2fa = True
                    target_list.append("2FA required - please enter your code")
                    
                # Check for successful login message
                if "[.] response type 6" in line:
                    wrapper_running = True
                    wrapper_needs_2fa = False
                    login_successful = True
                    if auto_login:
                        target_list.append("Auto-login successful. Ready for downloads.")
                    else:
                        target_list.append("Wrapper login successful. Ready for downloads.")
                        # Save credentials on successful manual login
                        if email and password:
                            if save_credentials(email, password):
                                target_list.append("Credentials saved for auto-login")
                            else:
                                target_list.append("Failed to save credentials")
                    
    except Exception as e:
        target_list.append(f"Error reading wrapper logs: {str(e)}")
    finally:
        # Check if process ended
        if wrapper_process and wrapper_process.poll() is not None:
            exit_code = wrapper_process.poll()
            if not login_successful:
                # Process ended before successful login
                target_list.append(f"Login failed - wrapper process exited with code: {exit_code}")
                wrapper_running = False
                wrapper_needs_2fa = False
                # Delete credentials on failed auto-login
                if auto_login:
                    target_list.append("Auto-login failed, deleting saved credentials")
                    delete_credentials()
            elif exit_code != 0:
                target_list.append(f"Wrapper process ended unexpectedly with exit code: {exit_code}")
                wrapper_running = False
                wrapper_needs_2fa = False
            else:
                target_list.append("Wrapper process ended normally")
                wrapper_running = False
                wrapper_needs_2fa = False
        pipe.close()

wrapper_logs = []
downloader_logs = []

def get_credentials_path():
    """Get the path to the credentials file"""
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(script_dir, ".credentials")

def save_credentials(email, password):
    """Save credentials to file (base64 encoded for basic obfuscation)"""
    try:
        credentials = {
            "email": base64.b64encode(email.encode()).decode(),
            "password": base64.b64encode(password.encode()).decode()
        }
        with open(get_credentials_path(), 'w') as f:
            json.dump(credentials, f)
        return True
    except Exception as e:
        print(f"Error saving credentials: {e}")
        return False

def load_credentials():
    """Load and decode saved credentials"""
    try:
        credentials_path = get_credentials_path()
        if os.path.exists(credentials_path):
            with open(credentials_path, 'r') as f:
                credentials = json.load(f)
            email = base64.b64decode(credentials["email"]).decode()
            password = base64.b64decode(credentials["password"]).decode()
            return email, password
    except Exception as e:
        print(f"Error loading credentials: {e}")
    return None, None

def delete_credentials():
    """Delete saved credentials"""
    try:
        credentials_path = get_credentials_path()
        if os.path.exists(credentials_path):
            os.remove(credentials_path)
        return True
    except Exception as e:
        print(f"Error deleting credentials: {e}")
        return False

def attempt_auto_login():
    """Try to automatically login with saved credentials"""
    email, password = load_credentials()
    if email and password:
        wrapper_logs.append("Found saved credentials, attempting auto-login...")
        return start_wrapper_login(email, password, auto_login=True)
    return False

def start_wrapper_login(email, password, auto_login=False):
    """Start wrapper login process"""
    global wrapper_process, wrapper_running, wrapper_logs
    
    if wrapper_process and wrapper_process.poll() is None:
        if not auto_login:
            wrapper_logs.append("Wrapper already running")
        return False

    if not auto_login:
        wrapper_logs = []  # reset logs only for manual login
    
    prefix = "Auto-login: " if auto_login else ""
    wrapper_logs.append(f"{prefix}Starting wrapper login for {email}...")
    
    # Use absolute path and proper command format
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    wrapper_dir = os.path.join(script_dir, "wrapper")
    wrapper_path = os.path.join(wrapper_dir, "wrapper")
    
    cmd = [wrapper_path, "-L", f"{email}:{password}"]
    wrapper_logs.append(f"{prefix}Executing: {' '.join(cmd)}")
    wrapper_logs.append(f"{prefix}Working directory: {wrapper_dir}")
    
    try:
        wrapper_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            bufsize=1,
            universal_newlines=True,
            cwd=wrapper_dir  # Run from wrapper directory
        )
        
        # Don't set wrapper_running=True yet, wait for the success message
        threading.Thread(target=stream_wrapper_logs, args=(wrapper_process.stdout, wrapper_logs, email, password, auto_login), daemon=True).start()
        
        wrapper_logs.append(f"{prefix}Wrapper process started, waiting for login confirmation...")
        return True
        
    except Exception as e:
        wrapper_logs.append(f"{prefix}Error starting wrapper: {str(e)}")
        if auto_login:
            wrapper_logs.append("Auto-login failed, deleting saved credentials")
            delete_credentials()
        return False


@app.route("/")
def index():
    # Check for saved credentials and attempt auto-login on first load
    email, password = load_credentials()
    if email and password and not wrapper_running and (not wrapper_process or wrapper_process.poll() is not None):
        # Attempt auto-login in a separate thread to not block page load
        threading.Thread(target=attempt_auto_login, daemon=True).start()
    
    return render_template("index.html", wrapper_running=wrapper_running, has_saved_credentials=email is not None, saved_email=email if email else "")


@app.route("/login_wrapper", methods=["POST"])
def login_wrapper():
    email = request.form.get("email")
    password = request.form.get("password")

    if wrapper_process and wrapper_process.poll() is None:
        return jsonify({"status": "error", "msg": "Wrapper already running"})

    if start_wrapper_login(email, password, auto_login=False):
        return jsonify({"status": "ok", "msg": "Wrapper process started, waiting for login..."})
    else:
        return jsonify({"status": "error", "msg": "Failed to start wrapper"})

@app.route("/submit_2fa", methods=["POST"])
def submit_2fa():
    global wrapper_process, wrapper_needs_2fa, wrapper_logs
    
    two_fa_code = request.form.get("twofa_code")
    
    if not wrapper_needs_2fa:
        return jsonify({"status": "error", "msg": "2FA not required"})
    
    if not wrapper_process or wrapper_process.poll() is not None:
        return jsonify({"status": "error", "msg": "Wrapper not running"})
    
    if not two_fa_code:
        return jsonify({"status": "error", "msg": "2FA code required"})
    
    try:
        # Send 2FA code to wrapper process
        wrapper_process.stdin.write(f"{two_fa_code}\n")
        wrapper_process.stdin.flush()
        wrapper_logs.append(f"Submitted 2FA code: {two_fa_code}")
        wrapper_needs_2fa = False
        return jsonify({"status": "ok", "msg": "2FA code submitted"})
    except Exception as e:
        wrapper_logs.append(f"❌ Error submitting 2FA code: {str(e)}")
        return jsonify({"status": "error", "msg": f"Failed to submit 2FA code: {str(e)}"})


@app.route("/download", methods=["POST"])
def download():
    global download_process, download_running, downloader_logs
    
    link = request.form.get("link")
    format_choice = request.form.get("format")
    special_audio = request.form.get("special_audio") == "true"
    
    if not wrapper_running:
        return jsonify({"status": "error", "msg": "Wrapper not running"})
    
    if download_running:
        return jsonify({"status": "error", "msg": "Download already in progress"})
    
    if not link:
        return jsonify({"status": "error", "msg": "No URL provided"})
    
    # Determine the command to run
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    amd_dir = os.path.join(script_dir, "apple-music-downloader")
    
    if special_audio:
        if format_choice == "ATMOS":
            cmd = ["go", "run", "main.go", "--atmos", link]
            downloader_logs.append(f"Starting ATMOS download: {link}")
        elif format_choice == "AAC":
            cmd = ["go", "run", "main.go", "--aac", link]
            downloader_logs.append(f"Starting AAC download: {link}")
        else:
            return jsonify({"status": "error", "msg": "Invalid format selected"})
    else:
        cmd = ["go", "run", "main.go", link]
        downloader_logs.append(f"Starting standard download: {link}")
    
    downloader_logs.append(f"Working directory: {amd_dir}")
    downloader_logs.append(f"Executing: {' '.join(cmd)}")
    
    try:
        download_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            universal_newlines=True,
            cwd=amd_dir  # Run from apple-music-downloader directory
        )
        
        download_running = True
        threading.Thread(target=stream_download_logs, args=(download_process.stdout, downloader_logs), daemon=True).start()
        
        return jsonify({"status": "ok", "msg": "Download started successfully"})
        
    except Exception as e:
        downloader_logs.append(f"Error starting download: {str(e)}")
        return jsonify({"status": "error", "msg": f"Failed to start download: {str(e)}"})


@app.route("/get_logs")
def get_logs():
    global wrapper_running, wrapper_process, download_running, download_process, wrapper_needs_2fa
    
    # Check if wrapper process is still running
    if wrapper_process and wrapper_process.poll() is not None:
        if wrapper_running:  # Process ended but we thought it was still running
            wrapper_running = False
    
    # Check if download process is still running
    if download_process and download_process.poll() is not None:
        if download_running:  # Process ended but we thought it was still running
            download_running = False
    
    return jsonify({
        "wrapper": wrapper_logs[-200:],  # last 200 lines
        "downloader": downloader_logs[-200:],
        "wrapper_running": wrapper_running,
        "download_running": download_running,
        "wrapper_needs_2fa": wrapper_needs_2fa
    })

@app.route("/stop_wrapper", methods=["POST"])
def stop_wrapper():
    global wrapper_process, wrapper_running, wrapper_logs, wrapper_needs_2fa
    
    if wrapper_process and wrapper_process.poll() is None:
        wrapper_process.terminate()
        wrapper_logs.append("Wrapper process terminated by user")
        wrapper_running = False
        wrapper_needs_2fa = False
        return jsonify({"status": "ok", "msg": "Wrapper stopped"})
    else:
        return jsonify({"status": "error", "msg": "Wrapper not running"})

@app.route("/settings")
def settings():
    return render_template("settings.html")

@app.route("/get_config")
def get_config():
    try:
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(script_dir, "apple-music-downloader", "config.yaml")
        
        with open(config_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
            return jsonify({"status": "ok", "config": config})
    except Exception as e:
        return jsonify({"status": "error", "msg": str(e)})

@app.route("/save_config", methods=["POST"])
def save_config():
    try:
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(script_dir, "apple-music-downloader", "config.yaml")
        
        config_data = request.json
        
        # Define fields that should be integers
        integer_fields = {
            'alac-max', 'atmos-max', 'limit-max', 'max-memory-limit', 'mv-max'
        }
        
        # Define fields that should be booleans
        boolean_fields = {
            'embed-lrc', 'save-lrc-file', 'save-artist-cover', 'save-animated-artwork',
            'emby-animated-artwork', 'embed-cover', 'get-m3u8-from-device',
            'use-songinfo-for-playlist', 'dl-albumcover-for-playlist',
            'convert-after-download', 'convert-keep-original', 'convert-skip-if-source-matches'
        }
        
        # Define fields that are folder paths and need Windows to WSL translation
        path_fields = {
            'alac-save-folder', 'atmos-save-folder', 'aac-save-folder'
        }
        
        def translate_path_to_wsl(path):
            """Translate Windows paths to WSL paths when saving config"""
            if not path:
                return path
            # Check if it's a Windows-style path (e.g., C:/, D:/)
            if len(path) >= 3 and path[1:3] == ':\\':
                # Convert C:\ to /mnt/c/
                drive = path[0].lower()
                rest = path[3:].replace('\\', '/')
                return f"/mnt/{drive}/{rest}"
            elif len(path) >= 3 and path[1:3] == ':/':
                # Convert C:/ to /mnt/c/
                drive = path[0].lower()
                rest = path[3:]
                return f"/mnt/{drive}/{rest}"
            return path
        
        # Convert data types properly
        for key, value in config_data.items():
            if key in integer_fields:
                try:
                    config_data[key] = int(value) if value else 0
                except (ValueError, TypeError):
                    config_data[key] = 0
            elif key in boolean_fields:
                # Handle boolean conversion
                if isinstance(value, str):
                    config_data[key] = value.lower() in ('true', '1', 'yes', 'on')
                else:
                    config_data[key] = bool(value)
            elif key in path_fields:
                # Translate Windows paths to WSL format
                config_data[key] = translate_path_to_wsl(str(value))
            # Strings remain as strings (default)
        
        with open(config_path, 'w', encoding='utf-8') as file:
            yaml.dump(config_data, file, default_flow_style=False, allow_unicode=True)
            
        return jsonify({"status": "ok", "msg": "Configuration saved successfully"})
    except Exception as e:
        return jsonify({"status": "error", "msg": str(e)})

@app.route("/check_saved_credentials")
def check_saved_credentials():
    """Check if saved credentials exist"""
    email, password = load_credentials()
    return jsonify({"has_credentials": email is not None, "email": email if email else ""})

@app.route("/delete_saved_credentials", methods=["POST"])
def delete_saved_credentials():
    """Delete saved credentials"""
    if delete_credentials():
        return jsonify({"status": "ok", "msg": "Saved credentials deleted"})
    else:
        return jsonify({"status": "error", "msg": "Failed to delete credentials"})

@app.route("/auto_login", methods=["POST"])
def auto_login():
    """Attempt auto-login with saved credentials"""
    if attempt_auto_login():
        return jsonify({"status": "ok", "msg": "Auto-login started"})
    else:
        return jsonify({"status": "error", "msg": "No saved credentials or login failed"})

@app.route("/get_download_folders")
def get_download_folders():
    """Get download folder paths from config with Windows to WSL path translation"""
    try:
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(script_dir, "apple-music-downloader", "config.yaml")
        
        with open(config_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
            
        # Paths are now already in correct format in config file, no need to translate
        folders = {
            "alac": config.get("alac-save-folder", "AM-DL downloads"),
            "atmos": config.get("atmos-save-folder", "AM-DL-Atmos downloads"),
            "aac": config.get("aac-save-folder", "AM-DL-AAC downloads")
        }
        
        return jsonify({"status": "ok", "folders": folders})
    except Exception as e:
        return jsonify({"status": "error", "msg": str(e)})
