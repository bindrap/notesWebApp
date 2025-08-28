#!/usr/bin/env python3
"""
NoteBot Web Application - Click-to-Run Version
(Perfect for hitting the ▶️ Play button in VS Code)
"""

import sys
import os
import subprocess
import requests
from pathlib import Path
from datetime import datetime

# === ENSURE WE'RE IN THE CORRECT DIRECTORY ===
# This helps when running via VS Code from another working directory
project_root = Path(__file__).parent
os.chdir(project_root)

# Add project root to Python path
sys.path.insert(0, str(project_root))

# === LOGGING FUNCTION ===
def log(message, level="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {level}: {message}"
    print(log_entry)

    # Write to log file
    log_dir = project_root / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"startup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(log_entry + "\n")
    except Exception as e:
        print(f"⚠️  Could not write to log file: {e}")


# === STARTUP CHECKS ===
def check_python_version():
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        log(f"❌ Python {version.major}.{version.minor} detected. Python 3.8+ required.", "ERROR")
        return False
    log(f"✅ Python {version.major}.{version.minor}.{version.micro} - OK")
    return True


def check_dependencies():
    dependencies = {
        "flask": "Flask",
        "flask_cors": "Flask-CORS",
        "requests": "requests",
        "mammoth": "mammoth",
        "PyPDF2": "PyPDF2",
        "PIL": "Pillow",
        "werkzeug": "Werkzeug",
        "docx": "python-docx"
    }

    missing = []
    for import_name, display_name in dependencies.items():
        try:
            __import__(import_name)
            log(f"✅ {display_name} ({import_name}) - OK")
        except ImportError as e:
            log(f"❌ Failed to import {import_name} ({display_name}): {e}", "ERROR")
            missing.append(display_name)

    if missing:
        log(f"❌ Missing packages: {', '.join(missing)}", "ERROR")
        log("💡 Run: pip install -r requirements.txt", "INFO")
        return False
    return True


def check_ollama_running():
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=10)
        if response.status_code == 200:
            log("✅ Ollama service - OK")
            return True
        else:
            log(f"❌ Ollama responded with status {response.status_code}", "ERROR")
            return False
    except requests.exceptions.ConnectionError:
        log("❌ Ollama is not running. Start it with: ollama serve", "ERROR")
        return False
    except Exception as e:
        log(f"❌ Error connecting to Ollama: {e}", "ERROR")
        return False


def ensure_models_installed():
    required_models = ["qwen2.5vl:7b", "qwen3:4b"]
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=10)
        installed_models = [model["name"] for model in response.json().get("models", [])]

        for model in required_models:
            if model not in installed_models:
                log(f"⚠️  Model {model} not found. Installing...", "WARN")
                result = subprocess.run(
                    ["ollama", "pull", model],
                    capture_output=True,
                    text=True,
                    timeout=1800,
                    encoding="utf-8",
                    errors="replace"  # Prevent encoding crashes
                )
                if result.returncode == 0:
                    log(f"✅ Successfully installed {model}")
                else:
                    log(f"❌ Failed to install {model}:\n{result.stderr}", "ERROR")
                    return False
            else:
                log(f"✅ Model {model} - OK")
        return True
    except Exception as e:
        log(f"❌ Error checking models: {e}", "ERROR")
        return False


def create_template_if_needed():
    template_path = project_root / "templates" / "index.html"
    if template_path.exists():
        log("✅ HTML template exists - OK")
        return True

    html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NoteBot - City of Windsor</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
        .container { max-width: 800px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; }
        .header { text-align: center; margin-bottom: 30px; }
        .upload-area { border: 2px dashed #ccc; padding: 40px; text-align: center; border-radius: 10px; }
        .btn { background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; }
        .btn:hover { background: #0056b3; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📝 NoteBot</h1>
            <p>City of Windsor - Note Enhancement Tool</p>
        </div>
        <div class="upload-area">
            <h3>Upload Your Files</h3>
            <p>This is a minimal interface. For full functionality, please use the complete web application.</p>
            <form action="/api/process" method="post" enctype="multipart/form-data">
                <input type="file" name="files" multiple accept="image/*,.txt,.doc,.docx,.pdf">
                <br><br>
                <button type="submit" class="btn">Process Files</button>
            </form>
        </div>
    </div>
</body>
</html>'''

    try:
        template_path.parent.mkdir(exist_ok=True)
        template_path.write_text(html_content, encoding="utf-8")
        log("🎨 Created minimal HTML template")
        return True
    except Exception as e:
        log(f"❌ Failed to create template: {e}", "ERROR")
        return False


# === START FLASK APP ===
def start_flask_app():
    try:
        import app
        # Ensure the module is loaded correctly
        log(f"📁 Loaded app from: {getattr(app, '__file__', 'unknown location')}")
        
        # Make sure `app.app` exists
        if not hasattr(app, 'app'):
            log("❌ The 'app.py' file must define 'app = Flask(__name__)'", "ERROR")
            log("💡 Example: from flask import Flask; app = Flask(__name__)", "INFO")
            sys.exit(1)

        log("🚀 Starting NoteBot web server on http://localhost:5000")
        log("💡 Press CTRL+C to stop")
        app.app.run(host="127.0.0.1", port=5000, debug=True, threaded=True)

    except KeyboardInterrupt:
        log("👋 NoteBot shut down gracefully.")
    except Exception as e:
        log(f"💥 Failed to start Flask app: {e}", "ERROR")
        sys.exit(1)


# === MAIN FLOW - Runs when you click ▶️ ===
if __name__ == "__main__":
    log("🚀 Starting NoteBot Web Application (One-Click Mode)")
    log(f"📁 Project Root: {project_root.absolute()}")

    # Create essential folders
    for folder in ["uploads", "outputs", "temp", "logs", "static", "templates"]:
        (project_root / folder).mkdir(exist_ok=True)

    # Run checks
    checks = [
        ("Python Version", check_python_version),
        ("Dependencies", check_dependencies),
        ("Ollama Service", check_ollama_running),
        ("AI Models", ensure_models_installed),
        ("HTML Template", create_template_if_needed),
    ]

    all_passed = True
    for name, func in checks:
        log(f"🔍 Checking {name}...")
        if not func():
            all_passed = False
            break

    if all_passed:
        log("🎉 All systems go! Launching NoteBot...")
        start_flask_app()
    else:
        log("🛑 Startup failed. Fix the errors above and try again.", "ERROR")
        sys.exit(1)