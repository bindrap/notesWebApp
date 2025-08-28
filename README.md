# 📝 NoteBot – City of Windsor AI Note Enhancement Tool

> **Transform handwritten notes, images, and documents into professional Markdown project plans — powered by AI.**

A sleek, branded web application that uses **Ollama**, **Qwen models**, and smart UI design to help City of Windsor employees digitize and enhance their notes in seconds.

## 🚀 Quick Start

### Prerequisites

1. **Python 3.8+** installed
2. **Ollama** installed and running locally
3. **Git** for version control

### Required Ollama Models

```bash
# Install required models
ollama pull qwen2.5vl:7b    # For OCR (images → text)
ollama pull phi3:mini       # For fast, clean text enhancement
```

### Installation Steps

1. **Clone or create your project directory:**
```bash
mkdir notebot-webapp
cd notebot-webapp
```

2. **Create the Python virtual environment:**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies:**
```bash
pip install -r requirements.txt
```

4. **Create the project structure:**
```
notebot-webapp/
├── start_notebot.py         # One-click startup with checks
├── app.py                   # Flask backend
├── requirements.txt         # Python dependencies
├── static/
│   └── images/
│       ├── windsorSunset.jpg    # Background
│       ├── windsorLogo.png      # Top-left logo
│       └── windsorCoatofArms.png # Favicon & bottom-right badge
├── templates/
│   └── index.html           # Branded web interface
├── uploads/                 # Temporary file storage
├── outputs/                 # Enhanced Markdown files
├── logs/                    # Startup & error logs
└── temp/                    # Processing temp files
```

5. **Start the application:**
```bash
python app.py
```

6. **Access the web interface:**
   - Open your browser to `http://localhost:5000`

## 🔧 Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# Flask Configuration
FLASK_ENV=production
SECRET_KEY=your-secret-key-here

# Ollama Configuration
OLLAMA_HOST=http://localhost:11434
OCR_MODEL=qwen2.5vl:7b
ENHANCEMENT_MODEL=qwen3:4b

# File Upload Limits
MAX_FILE_SIZE=50MB
MAX_FILES_PER_BATCH=20

# Cleanup Configuration
AUTO_CLEANUP_HOURS=24
KEEP_RESULTS_DAYS=7

# City of Windsor Branding
ORGANIZATION_NAME="City of Windsor"
PRIMARY_COLOR="#2b6cb0"
```

### Model Configuration

Edit the model settings in `app.py`:

```python
# Model Configuration
OCR_MODEL = "qwen2.5vl:7b"      # Best for handwriting OCR
ENHANCEMENT_MODEL = "qwen3:4b"   # Fast text enhancement

# Alternative models you can use:
# OCR_MODEL = "llama3.2-vision"  # Alternative vision model
# ENHANCEMENT_MODEL = "qwen3:8b"  # Higher quality but slower
```

## 🖥️ Production Deployment

### Option 1: Local Server Deployment

For internal City of Windsor network deployment:

1. **Configure for production:**
```python
# In app.py, change the final lines to:
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
```

2. **Use a production WSGI server:**
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

3. **Set up reverse proxy with Nginx (optional):**
```nginx
server {
    listen 80;
    server_name notebot.cityofwindsor.local;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Option 2: Docker Deployment

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libopencv-dev \
    python3-opencv \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p uploads outputs temp logs

EXPOSE 5000

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]
```

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  notebot:
    build: .
    ports:
      - "5000:5000"
    volumes:
      - ./uploads:/app/uploads
      - ./outputs:/app/outputs
      - ./logs:/app/logs
    environment:
      - OLLAMA_HOST=http://host.docker.internal:11434
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    depends_on:
      - notebot
    restart: unless-stopped
```

## 🔒 Security Considerations

### File Upload Security

```python
# Secure file upload configuration
ALLOWED_EXTENSIONS = {'.txt', '.doc', '.docx', '.pdf', '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff'}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
MAX_FILES_PER_REQUEST = 20

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
```

### Access Control

For internal City network deployment:

```python
# IP whitelist for City of Windsor network
ALLOWED_IPS = [
    '192.168.1.0/24',    # Internal network range
    '10.0.0.0/8',        # Private network range
]

@app.before_request
def limit_remote_addr():
    if not any(ipaddress.ip_address(request.remote_addr) in ipaddress.ip_network(allowed_ip) 
               for allowed_ip in ALLOWED_IPS):
        abort(403)  # Forbidden
```

## 📊 Monitoring and Logging

### Application Monitoring

```python
# Add to app.py for better monitoring
import structlog
from datetime import datetime

logger = structlog.get_logger()

@app.route('/api/health')
def health_check():
    """Comprehensive health check"""
    try:
        # Check Ollama connection
        ollama_response = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        ollama_healthy = ollama_response.status_code == 200
        
        # Check disk space
        upload_space = shutil.disk_usage(UPLOAD_FOLDER)
        output_space = shutil.disk_usage(OUTPUT_FOLDER)
        
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'ollama_status': 'connected' if ollama_healthy else 'disconnected',
            'active_tasks': len(processing_tasks),
            'disk_usage': {
                'uploads_free_gb': upload_space.free / (1024**3),
                'outputs_free_gb': output_space.free / (1024**3)
            },
            'models': {
                'ocr': OCR_MODEL,
                'enhancement': ENHANCEMENT_MODEL
            }
        })
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500
```

### Log Rotation

```python
import logging.handlers

def setup_logging():
    """Configure rotating file handler"""
    log_formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
    )
    
    file_handler = logging.handlers.RotatingFileHandler(
        'logs/notebot.log', 
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setFormatter(log_formatter)
    file_handler.setLevel(logging.INFO)
    
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
```

## 🔧 Maintenance

### Automated Cleanup

Add to `app.py`:

```python
import threading
import schedule
import time

def cleanup_old_files():
    """Clean up files older than configured retention period"""
    retention_days = 7  # Keep files for 7 days
    cutoff_time = time.time() - (retention_days * 24 * 60 * 60)
    
    for folder in [UPLOAD_FOLDER, OUTPUT_FOLDER, TEMP_FOLDER]:
        for file_path in folder.glob("*"):
            if file_path.is_file() and file_path.stat().st_mtime < cutoff_time:
                try:
                    file_path.unlink()
                    logger.info(f"Cleaned up old file: {file_path}")
                except Exception as e:
                    logger.error(f"Failed to clean up {file_path}: {e}")

# Schedule cleanup to run daily at 2 AM
schedule.every().day.at("02:00").do(cleanup_old_files)

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(3600)  # Check every hour

# Start scheduler in background thread
scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
scheduler_thread.start()
```

## 🐛 Troubleshooting

### Common Issues

1. **Ollama Connection Failed**
   ```bash
   # Check if Ollama is running
   ollama list
   
   # Restart Ollama service
   systemctl restart ollama  # On Linux
   ```

2. **Model Not Found**
   ```bash
   # Pull missing models
   ollama pull qwen2.5vl:7b
   ollama pull qwen3:4b
   ```

3. **File Upload Errors**
   - Check file size limits in `app.py`
   - Verify file permissions on upload directory
   - Check disk space availability

4. **Memory Issues**
   - Reduce batch size for large files
   - Consider using smaller models for low-memory systems
   - Monitor system resources during processing

### Debug Mode

Enable debug logging:

```python
# In app.py
import logging
logging.basicConfig(level=logging.DEBUG)
app.config['DEBUG'] = True
```

### Performance Optimization

```python
# Add these optimizations to app.py

# Limit concurrent processing tasks
MAX_CONCURRENT_TASKS = 3
processing_semaphore = threading.Semaphore(MAX_CONCURRENT_TASKS)

# Add caching for repeated text enhancement
from functools import lru_cache

@lru_cache(maxsize=100)
def cached_enhance_text(text_hash, options_str):
    """Cache enhanced text results"""
    return processor.enhance_notes_with_ai(text, eval(options_str))
```

## 📋 API Documentation

### Endpoints

- `POST /api/process` - Process uploaded files
- `GET /api/status/<task_id>` - Check processing status
- `GET /api/download/<task_id>/<filename>` - Download processed file
- `GET /api/download-all/<task_id>` - Download all files as ZIP
- `DELETE /api/cleanup/<task_id>` - Clean up task files
- `GET /api/health` - System health check

### Request/Response Examples

**Process Files:**
```bash
curl -X POST -F "files=@note1.jpg" -F "files=@document.docx" \
     -F "cleanup=true" -F "summary=true" \
     http://localhost:5000/api/process
```

**Check Status:**
```bash
curl http://localhost:5000/api/status/task-uuid-here
```

