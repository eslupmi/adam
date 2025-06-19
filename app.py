from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import subprocess
import json
import os
from datetime import datetime
from typing import List, Optional
import uvicorn

app = FastAPI(title="ADAM - Alerts generator", version="1.0.0")

# Default Alertmanager URL
ALERTMANAGER_URL = os.environ.get('ALERTMANAGER_URL', 'http://localhost:9093')

# File to store form history
HISTORY_FILE = 'form_history.json'

# Templates
templates = Jinja2Templates(directory="templates")

def load_form_history():
    """Load form field history from JSON file"""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {
        'summaries': [],
        'descriptions': [],
        'services': [],
        'severities': [],
        'durations': [],
        'custom_labels': [],
        'custom_annotations': []
    }

def save_form_history(history):
    """Save form field history to JSON file"""
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)

def add_to_history(history, field, value):
    """Add value to history list if not already present"""
    if value and value not in history[field]:
        history[field].insert(0, value)
        # Keep only last 10 entries
        history[field] = history[field][:10]

def send_alert_with_amtool(summary, description, severity, duration, service, custom_labels, custom_annotations):
    """Send alert using amtool command"""
    try:
        # Build amtool command with correct format
        cmd = [
            'amtool', 'alert', 'add', summary,
            f'severity={severity}',
            f'service={service}',
            f'--annotation=summary="{summary}"',
            f'--annotation=description="{description}"',
            f'--annotation=duration="{duration}"',
            f'--alertmanager.url={ALERTMANAGER_URL}'
        ]
        
        # Add custom labels
        for label_key, label_value in custom_labels.items():
            if label_key and label_value:
                cmd.append(f'{label_key}={label_value}')
        
        # Add custom annotations
        for annotation_key, annotation_value in custom_annotations.items():
            if annotation_key and annotation_value:
                cmd.append(f'--annotation={annotation_key}="{annotation_value}"')
        
        print(f"Executing command: {' '.join(cmd)}")  # Debug output
        
        # Execute amtool command
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            return True, "Alert sent successfully"
        else:
            return False, f"Failed to send alert: {result.stderr}"
            
    except subprocess.TimeoutExpired:
        return False, "Timeout while sending alert"
    except FileNotFoundError:
        return False, "amtool command not found. Please install Alertmanager tools."
    except Exception as e:
        return False, f"Error sending alert: {str(e)}"

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main page with alert form"""
    history = load_form_history()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "history": history,
        "alertmanager_url": ALERTMANAGER_URL,
        "message": None,
        "message_type": None,
        "form_data": {
            'summary': '',
            'description': '',
            'severity': '',
            'duration': '',
            'service': '',
            'custom_labels': {},
            'custom_annotations': {}
        }
    })

@app.post("/", response_class=HTMLResponse)
async def send_alert(
    request: Request,
    summary: str = Form(...),
    description: str = Form(...),
    severity: str = Form(...),
    duration: str = Form(...),
    service: str = Form(...),
    label_keys: List[str] = Form([]),
    label_values: List[str] = Form([]),
    annotation_keys: List[str] = Form([]),
    annotation_values: List[str] = Form([])
):
    """Handle alert form submission"""
    history = load_form_history()
    
    # Get custom labels
    custom_labels = {}
    for i, key in enumerate(label_keys):
        if i < len(label_values) and key.strip() and label_values[i].strip():
            custom_labels[key.strip()] = label_values[i].strip()
    
    # Get custom annotations
    custom_annotations = {}
    for i, key in enumerate(annotation_keys):
        if i < len(annotation_values) and key.strip() and annotation_values[i].strip():
            custom_annotations[key.strip()] = annotation_values[i].strip()
    
    # Validate required fields
    if not all([summary.strip(), description.strip(), severity.strip(), duration.strip(), service.strip()]):
        return templates.TemplateResponse("index.html", {
            "request": request,
            "history": history,
            "alertmanager_url": ALERTMANAGER_URL,
            "message": "All required fields must be filled",
            "message_type": "error",
            "form_data": {
                'summary': summary,
                'description': description,
                'severity': severity,
                'duration': duration,
                'service': service,
                'custom_labels': custom_labels,
                'custom_annotations': custom_annotations
            }
        })
    
    if severity not in ['info', 'warning', 'critical']:
        return templates.TemplateResponse("index.html", {
            "request": request,
            "history": history,
            "alertmanager_url": ALERTMANAGER_URL,
            "message": "Invalid severity level",
            "message_type": "error",
            "form_data": {
                'summary': summary,
                'description': description,
                'severity': severity,
                'duration': duration,
                'service': service,
                'custom_labels': custom_labels,
                'custom_annotations': custom_annotations
            }
        })
    
    # Send alert using amtool
    success, message = send_alert_with_amtool(
        summary.strip(), 
        description.strip(), 
        severity.strip(),
        duration.strip(),
        service.strip(), 
        custom_labels,
        custom_annotations
    )
    
    if success:
        # Update history
        add_to_history(history, 'summaries', summary.strip())
        add_to_history(history, 'descriptions', description.strip())
        add_to_history(history, 'services', service.strip())
        add_to_history(history, 'severities', severity.strip())
        add_to_history(history, 'durations', duration.strip())
        save_form_history(history)
        
        return templates.TemplateResponse("index.html", {
            "request": request,
            "history": history,
            "alertmanager_url": ALERTMANAGER_URL,
            "message": message,
            "message_type": "success",
            "form_data": {
                'summary': '',
                'description': '',
                'severity': '',
                'duration': '',
                'service': '',
                'custom_labels': {},
                'custom_annotations': {}
            }
        })
    else:
        return templates.TemplateResponse("index.html", {
            "request": request,
            "history": history,
            "alertmanager_url": ALERTMANAGER_URL,
            "message": message,
            "message_type": "error",
            "form_data": {
                'summary': summary,
                'description': description,
                'severity': severity,
                'duration': duration,
                'service': service,
                'custom_labels': custom_labels,
                'custom_annotations': custom_annotations
            }
        })

if __name__ == "__main__":
    port = int(os.environ.get("ADAM_PORT", 5067))
    uvicorn.run(app, host="0.0.0.0", port=port)
