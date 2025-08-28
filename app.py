"""
NoteBot Flask Application
Serves the web interface and handles file processing requests.
Integrates OCR, AI structuring, and markdown enhancement.
"""

from flask import Flask, request, jsonify, render_template_string
import os
import base64
import requests
import subprocess
import sys
from pathlib import Path
import docx
import PyPDF2
from PIL import Image
import mammoth
import tempfile
import re

# === CONFIGURATION ===
project_root = Path(__file__).parent
uploads_dir = project_root / "uploads"
outputs_dir = project_root / "outputs"
temp_dir = project_root / "temp"
logs_dir = project_root / "logs"

# Create required directories
for folder in [uploads_dir, outputs_dir, temp_dir, logs_dir]:
    folder.mkdir(exist_ok=True)

# Ollama config
OLLAMA_HOST = "http://localhost:11434"
VISION_MODEL = "qwen2.5vl:7b"   # For OCR (images)
TEXT_MODEL = "phi3:mini"            #"qwen3:4b"         # For structuring notes
TEMPERATURE = 0.1

# === FLASK APP ===
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max upload size


# === TEXT EXTRACTION FUNCTIONS ===
def extract_text_from_txt(filepath):
    try:
        return Path(filepath).read_text(encoding="utf-8")
    except Exception as e:
        return f"[ERROR: Could not read TXT] {str(e)}"

def extract_text_from_docx(filepath):
    try:
        with open(filepath, "rb") as f:
            result = mammoth.extract_raw_text(f)
            return result.value.strip()
    except Exception as e:
        return f"[ERROR: Could not read DOCX] {str(e)}"

def extract_text_from_pdf(filepath):
    try:
        reader = PyPDF2.PdfReader(str(filepath))
        return "\n".join([page.extract_text() or "" for page in reader.pages])
    except Exception as e:
        return f"[ERROR: Could not read PDF] {str(e)}"

def image_to_text_ocr(image_path: Path) -> str:
    """Use qwen2.5vl:7b to transcribe image to text."""
    try:
        img_bytes = image_path.read_bytes()
        img_b64 = base64.b64encode(img_bytes).decode("utf-8")

        prompt = (
            "You are a precise OCR assistant.\n"
            "Transcribe ALL visible text exactly as written.\n"
            "- Preserve line breaks, punctuation, and formatting.\n"
            "- Do NOT add explanations, headers, or commentary.\n"
            "- Output ONLY the raw text."
        )

        payload = {
            "model": VISION_MODEL,
            "prompt": prompt,
            "images": [img_b64],
            "stream": False,
            "options": {"temperature": 0.0},
        }

        response = requests.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=600)
        response.raise_for_status()
        return response.json().get("response", "").strip()

    except Exception as e:
        return f"[OCR ERROR] {str(e)}"

def text_to_project_notes(raw_text: str) -> str:
    """
    Converts raw notes into a clean, structured markdown project plan.
    Uses a strict prompt + post-processing to guarantee format.
    """
    try:
        # 🎯 Simple, direct prompt — no room for AI to "think"
        prompt = f"""
You are a markdown-only assistant that creates project plans.
Follow these rules:
- Start with "# Project Title"
- Include exactly these sections in order:
  ## Goals / Objectives
  ## Key Features or Deliverables
  ...
- Output ONLY the raw markdown — no explanations, no commentary
- Do NOT wrap the output in ```markdown or any code block
- Do NOT include triple backticks (```)
- If information is missing, make reasonable assumptions

Raw notes:
{raw_text}

Now write the plan:
# Project Title
"""

        payload = {
            "model": TEXT_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1, "num_ctx": 4096}
        }

        # 📡 Send to Ollama
        response = requests.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=600)
        response.raise_for_status()
        ai_output = response.json().get("response", "").strip()

        # 🧹 CLEANING: Extract from "# Project Title" if needed
        start_idx = ai_output.find("# Project Title")
        if start_idx != -1:
            ai_output = ai_output[start_idx:]

        # 🔍 Normalize section headers
        lines = [line.strip() for line in ai_output.splitlines() if line.strip()]

        # 🏗️ Rebuild with guaranteed structure
        final_lines = []
        seen_sections = {"Project Title": False}
        current_section = None

        # Track required sections
        required_sections = [
            "Goals / Objectives",
            "Key Features or Deliverables",
            "Tasks and Steps",
            "Estimated Timeline / Deadlines",
            "Resources / Tools Needed",
            "Potential Risks / Challenges",
            "Next Actions"
        ]

        # First, add title (must be first)
        title_lines = []
        for line in lines:
            if line.startswith("# "):
                continue  # skip header line, we'll add it
            if line.startswith("## "):
                break
            title_lines.append(f"- {line}" if not line.startswith(("-", "*")) else line)
        final_lines.append("# Project Title")
        final_lines.extend(title_lines or ["- Project enhancement"])

        # Then, process each required section
        for section in required_sections:
            header = f"## {section}"
            content = []

            # Look for this section in AI output
            in_section = False
            for line in lines:
                if line == header:
                    in_section = True
                    continue
                if in_section and line.startswith("## "):
                    break  # next section
                if in_section:
                    if line.startswith("- ") or line.startswith("* ") or line[0].isdigit():
                        content.append(line)
                    else:
                        content.append(f"- {line}")

            # Add section (even if empty)
            final_lines.append(header)
            final_lines.extend(content or [f"- {placeholder_text[section]}"])
            
        return "\n".join(final_lines)

    except Exception as e:
        # 🛡️ Fallback: return clean markdown even on error
        return f"""# Project Title
- AI Processing Failed

## Goals / Objectives
- Input too large or model unreachable

## Key Features or Deliverables
- Check Ollama and retry

## Tasks and Steps
- Reduce input size
- Try simpler model

## Estimated Timeline / Deadlines
- Immediate

## Resources / Tools Needed
- Stable connection to Ollama

## Potential Risks / Challenges
- Timeout or model crash

## Next Actions
- Retry with shorter input
"""


# 📝 Placeholders for missing sections
placeholder_text = {
    "Goals / Objectives": "Define the main purpose and goals.",
    "Key Features or Deliverables": "List expected outputs or features.",
    "Tasks and Steps": "Break down the work into steps.",
    "Estimated Timeline / Deadlines": "Set realistic deadlines.",
    "Resources / Tools Needed": "Identify required tools or access.",
    "Potential Risks / Challenges": "Note possible obstacles.",
    "Next Actions": "List immediate next steps."
}


def extract_text(filepath):
    ext = Path(filepath).suffix.lower()

    if ext in [".txt"]:
        return extract_text_from_txt(filepath)
    elif ext in [".doc", ".docx"]:
        return extract_text_from_docx(filepath)
    elif ext == ".pdf":
        return extract_text_from_pdf(filepath)
    elif ext in [".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"]:
        return image_to_text_ocr(Path(filepath))
    else:
        return f"[UNSUPPORTED FILE TYPE: {ext}] File not processed."

# === ROUTES ===

@app.route("/")
def home():
    """Serve the main HTML page"""
    try:
        template_path = project_root / "templates" / "index.html"
        if template_path.exists():
            return template_path.read_text(encoding="utf-8")
        else:
            return render_template_string("""
                <h1>📝 NoteBot</h1>
                <p>Upload support requires <code>templates/index.html</code>.</p>
            """)
    except Exception as e:
        return f"<h1>📝 NoteBot</h1><p>Error loading page: {e}</p>", 500


@app.route("/api/process", methods=["POST"])
def process_files():
    """Handle file uploads, extract text, and enhance with AI."""
    import logging as py_logging
    py_logging.basicConfig(level=py_logging.INFO)

    if "files" not in request.files:
        return jsonify({"error": "No file part in request"}), 400

    files = request.files.getlist("files")
    if not files or all(f.filename == "" for f in files):
        return jsonify({"error": "No selected files"}), 400

    results = []

    for file in files:
        if not file or not file.filename:
            continue

        filename = file.filename
        temp_path = uploads_dir / filename
        counter = 1
        while temp_path.exists():
            temp_path = uploads_dir / f"{Path(filename).stem}_{counter}{Path(filename).suffix}"
            counter += 1
        file.save(temp_path)
        py_logging.info(f"✅ Saved upload: {temp_path}")

        # Step 1: Extract text
        try:
            raw_text = extract_text(temp_path)
            py_logging.info(f"📄 Extracted text (first 200 chars): {raw_text[:200]}")
        except Exception as e:
            error_msg = f"Extract failed: {str(e)}"
            py_logging.error(error_msg)
            results.append({
                "filename": filename,
                "status": "failed",
                "error": error_msg
            })
            continue

        if raw_text.startswith("[ERROR") or "[UNSUPPORTED" in raw_text:
            results.append({
                "filename": filename,
                "status": "failed",
                "error": raw_text
            })
            continue

        # Step 2: Send to AI for structuring
        try:
            py_logging.info("🧠 Sending to AI for structuring...")
            enhanced_notes = text_to_project_notes(raw_text)
            py_logging.info("✅ AI responded successfully.")

            # Save to outputs folder
            output_path = outputs_dir / f"{Path(filename).stem}.md"
            output_path.write_text(enhanced_notes, encoding="utf-8")

            results.append({
                "filename": filename,
                "status": "success",
                "raw_text_preview": raw_text[:300],
                "enhanced_notes": enhanced_notes
            })
        except requests.exceptions.Timeout:
            error = "❌ AI timeout: Model took too long to respond (increase timeout?)"
            py_logging.error(error)
            results.append({"filename": filename, "status": "failed", "error": error})
        except requests.exceptions.RequestException as e:
            error = f"❌ Ollama API error: {str(e)}"
            py_logging.error(error)
            results.append({"filename": filename, "status": "failed", "error": error})
        except Exception as e:
            error = f"❌ Unexpected error during AI processing: {str(e)}"
            py_logging.error(error)
            results.append({"filename": filename, "status": "failed", "error": error})

    return jsonify({
        "message": "Processing completed",
        "results": results
    })

@app.route("/health")
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "NoteBot"})


# === DEV RUNNER ===
if __name__ == "__main__":
    print("💡 Tip: Use 'start_notebot.py' to run with full startup checks.")
    app.run(host="127.0.0.1", port=5000, debug=True)