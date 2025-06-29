from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import json
import os
import asyncio
from datetime import datetime, timedelta
from typing import List, Optional
import uvicorn
import requests

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

def send_alert_with_curl(summary, description, severity, duration, service, custom_labels, custom_annotations):
    """Send alert using curl command to Alertmanager API"""
    try:
        # Generate ISO8601 timestamps
        now = datetime.utcnow()
        starts_at = (now - timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # Prepare the alert payload in the same format as the working bash script
        alert_data = [
            {
                "labels": {
                    "alertname": summary,
                    "severity": severity,
                    "service": service
                },
                "annotations": {
                    "summary": summary,
                    "description": description
                },
                "startsAt": starts_at,
                "endsAt": None
            }
        ]
        
        # Add custom labels
        for label_key, label_value in custom_labels.items():
            if label_key and label_value:
                alert_data[0]["labels"][label_key] = label_value
        
        # Add custom annotations
        for annotation_key, annotation_value in custom_annotations.items():
            if annotation_key and annotation_value:
                alert_data[0]["annotations"][annotation_key] = annotation_value
        
        # Prepare headers
        headers = {
            'Content-Type': 'application/json'
        }
        
        # Send POST request to Alertmanager
        alertmanager_api_url = f"{ALERTMANAGER_URL}/api/v2/alerts"
        print(f"Sending alert to: {alertmanager_api_url}")
        print(f"Alert data: {json.dumps(alert_data, indent=2)}")
        
        response = requests.post(
            alertmanager_api_url,
            json=alert_data,
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            return True, "Alert sent successfully"
        else:
            return False, f"Failed to send alert: HTTP {response.status_code} - {response.text}"
            
    except requests.exceptions.Timeout:
        return False, "Timeout while sending alert"
    except requests.exceptions.ConnectionError:
        return False, f"Connection error. Cannot connect to Alertmanager at {ALERTMANAGER_URL}"
    except Exception as e:
        return False, f"Error sending alert: {str(e)}"

def send_resolved_alert_with_curl(summary, description, severity, service, custom_labels, custom_annotations):
    """Send resolved alert using curl command to Alertmanager API"""
    try:
        # Generate ISO8601 timestamps
        now = datetime.utcnow()
        starts_at = (now - timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        ends_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # Prepare the resolved alert payload
        alert_data = [
            {
                "labels": {
                    "alertname": summary,
                    "severity": severity,
                    "service": service
                },
                "annotations": {
                    "summary": summary,
                    "description": description
                },
                "startsAt": starts_at,
                "endsAt": ends_at
            }
        ]
        
        # Add custom labels
        for label_key, label_value in custom_labels.items():
            if label_key and label_value:
                alert_data[0]["labels"][label_key] = label_value
        
        # Add custom annotations
        for annotation_key, annotation_value in custom_annotations.items():
            if annotation_key and annotation_value:
                alert_data[0]["annotations"][annotation_key] = annotation_value
        
        # Prepare headers
        headers = {
            'Content-Type': 'application/json'
        }
        
        # Send POST request to Alertmanager
        alertmanager_api_url = f"{ALERTMANAGER_URL}/api/v2/alerts"
        print(f"Sending resolved alert to: {alertmanager_api_url}")
        print(f"Resolved alert data: {json.dumps(alert_data, indent=2)}")
        
        response = requests.post(
            alertmanager_api_url,
            json=alert_data,
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            return True, "Resolved alert sent successfully"
        else:
            return False, f"Failed to send resolved alert: HTTP {response.status_code} - {response.text}"
            
    except requests.exceptions.Timeout:
        return False, "Timeout while sending resolved alert"
    except requests.exceptions.ConnectionError:
        return False, f"Connection error. Cannot connect to Alertmanager at {ALERTMANAGER_URL}"
    except Exception as e:
        return False, f"Error sending resolved alert: {str(e)}"

async def auto_resolve_alert(duration_str, summary, description, severity, service, custom_labels, custom_annotations):
    """Automatically resolve alert after specified duration"""
    try:
        # Parse duration string to seconds
        duration_seconds = parse_duration_to_seconds(duration_str)
        
        # Wait for the specified duration
        await asyncio.sleep(duration_seconds)
        
        # Send resolved alert
        success, message = send_resolved_alert_with_curl(
            summary, description, severity, service, custom_labels, custom_annotations
        )
        
        if success:
            print(f"Auto-resolved alert: {summary}")
        else:
            print(f"Failed to auto-resolve alert: {summary} - {message}")
            
    except Exception as e:
        print(f"Error in auto-resolve task for alert {summary}: {str(e)}")

def parse_duration_to_seconds(duration_str):
    """Parse duration string (e.g., '10s', '1m', '5m', '1h') to seconds"""
    if duration_str.endswith('s'):
        return int(duration_str[:-1])
    elif duration_str.endswith('m'):
        return int(duration_str[:-1]) * 60
    elif duration_str.endswith('h'):
        return int(duration_str[:-1]) * 3600
    else:
        # Default to 5 minutes if format is unknown
        return 300

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
    
    # Send alert using curl
    success, message = send_alert_with_curl(
        summary.strip(), 
        description.strip(), 
        severity.strip(),
        duration.strip(),
        service.strip(), 
        custom_labels,
        custom_annotations
    )
    
    if success:
        # Start auto-resolve task
        asyncio.create_task(auto_resolve_alert(
            duration.strip(),
            summary.strip(),
            description.strip(),
            severity.strip(),
            service.strip(),
            custom_labels,
            custom_annotations
        ))
        
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
