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
TEXT_MODEL = "phi3:mini"         #"phi3:mini"  #"qwen3:4b"         # For structuring notes
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
    Uses a smart AI to turn raw notes into polished, insightful markdown.
    Focuses on clarity, next steps, and professional tone.
    """
    try:
        prompt = f"""<|im_start|>system
You are a senior project assistant with 10+ years of experience.
Your job is to transform messy, incomplete notes into clear, actionable, professional documents.

Do NOT use templates or fixed sections.
Instead, use your judgment to structure the output based on the content.

You MUST:
- Do not include thinking in the project notes output, user just want notes not thinking attached
- Preserve all key information
- Clarify ambiguous points with reasonable assumptions
- Add logical structure (headings, lists, etc.)
- Include a "Next Steps" section at the end
- Use markdown formatting appropriately
- Write in a professional but conversational tone
- NEVER say 'thinking', 'note', or 'here is the plan'
- Output ONLY the enhanced notes — nothing else

Now enhance these raw notes:
<|im_end|>

<|im_start|>user
{raw_text}
<|im_end|>

<|im_start|>assistant
"""

        payload = {
            "model": TEXT_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": TEMPERATURE, "num_ctx": 8192}
        }

        response = requests.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=600)
        response.raise_for_status()
        enhanced = response.json().get("response", "").strip()

        # Clean up any accidental prefixes
        enhanced = re.sub(r"^(Here is|The|Below is|Enhanced version).*?\n", "", enhanced, flags=re.IGNORECASE | re.MULTILINE).strip()

        # Ensure there's a "Next Steps" or "Action Items" section
        if not re.search(r"##\s*(Next Steps|Action Items|To-Do|What's Next)", enhanced, re.IGNORECASE):
            enhanced += "\n\n## Next Steps\n- Review and confirm action items\n- Assign owners and deadlines"

        return enhanced

    except Exception as e:
        return f"""# Note Enhancement Failed

The AI could not process your notes.

**Error:** {str(e)}

Please try again with a shorter note or check the Ollama service."""


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