from fastapi import FastAPI, Request, Form, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import json
import os
import sys
import asyncio
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Set
import uvicorn
import requests
from dotenv import load_dotenv
import random

# Load environment variables from .env file
load_dotenv()

app = FastAPI(title="ADAM - Alerts generator", version="1.0.0")

# Configure logging with environment variable support
log_level = os.environ.get('LOG_LEVEL', 'INFO')
log_level_map = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL
}

# Get log level, default to DEBUG if invalid
level = log_level_map.get(log_level, logging.DEBUG)

logging.basicConfig(
    level=level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# Log the configured log level
logger.info(f"Logging initialized with level: {logging.getLevelName(level)} (from LOG_LEVEL: {log_level})")

# Default Alertmanager URL
ALERTMANAGER_URL = os.environ.get('ALERTMANAGER_URL', 'http://localhost:9093')

# File to store form history
HISTORY_FILE = 'form_history.json'

# Directory to store sent alerts for auto-resolve
ALERTS_DIR = 'alerts'

# Ensure alerts directory exists
os.makedirs(ALERTS_DIR, exist_ok=True)
logger.debug(f"Alerts directory created/verified: {ALERTS_DIR}")

# Templates
templates = Jinja2Templates(directory="templates")

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)

    async def broadcast(self, message: dict):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send WebSocket message: {e}")
                disconnected.append(connection)
        
        for connection in disconnected:
            self.disconnect(connection)

manager = ConnectionManager()

# In-memory storage for all alerts
alerts_storage: dict = {}

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

def generate_random_alertname():
    """Generate random alertname using noun + adjective pattern"""
    summary_nouns = [
        "Database", "Connection", "Memory", "CPU", "Disk", "Network", "Service", "API", "Cache", "Queue",
        "Timeout", "Error", "Failure", "Warning", "Critical", "Overflow", "Underflow", "Server", "Client", "Process"
    ]
    
    summary_adjectives = [
        "High", "Low", "Critical", "Warning", "Error", "Failed", "Slow", "Fast", "Overloaded", "Underutilized",
        "Broken", "Unstable", "Degraded", "Unavailable", "Responsive", "Unresponsive", "Healthy", "Unhealthy"
    ]
    
    return f"{random.choice(summary_nouns)}{random.choice(summary_adjectives)}"

def generate_random_label_value(label_key: str):
    """Generate random value for a label based on its key"""
    label_key_lower = label_key.lower()
    
    if 'service' in label_key_lower:
        service_names = [
            "auth-service", "api-gateway", "user-service", "payment-service", "notification-service",
            "database-service", "cache-service", "queue-service", "storage-service", "monitoring-service",
            "frontend-app", "backend-api", "mobile-api", "admin-panel", "analytics-service",
            "search-service", "email-service", "sms-service", "file-service", "log-service"
        ]
        return random.choice(service_names)
    elif 'environment' in label_key_lower or 'env' in label_key_lower:
        return random.choice(["production", "staging", "development", "testing"])
    elif 'team' in label_key_lower:
        return random.choice(["devops", "backend", "frontend", "qa", "security"])
    elif 'region' in label_key_lower:
        return random.choice(["us-east", "us-west", "eu-west", "eu-central", "asia-pacific"])
    else:
        return f"value-{random.randint(1, 1000)}"

def send_alert_with_curl(alertname, summary, description, severity, duration, service, custom_labels, custom_annotations):
    """Send alert using curl command to Alertmanager API"""
    logger.debug(f"Starting alert sending process - Summary: '{summary}', Severity: '{severity}', Service: '{service}'")
    
    try:
        # Generate ISO8601 timestamps
        now = datetime.now(timezone.utc)
        starts_at = (now - timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        logger.debug(f"Generated timestamps - Now: {now}, StartsAt: {starts_at}")
        
        # Prepare the alert payload in the same format as the working bash script
        alert_data = [
            {
                "labels": {
                    "alertname": alertname or "Alert",
                    "severity": severity,
                    "service": service or "unknown"
                },
                "annotations": {},
                "startsAt": starts_at,
                "endsAt": None
            }
        ]
        
        # Add custom labels
        for label_key, label_value in custom_labels.items():
            if label_key and label_value:
                alert_data[0]["labels"][label_key] = label_value
                logger.debug(f"Added custom label: '{label_key}' = '{label_value}'")
        
        # Add custom annotations (only if they have values)
        for annotation_key, annotation_value in custom_annotations.items():
            if annotation_key and annotation_value:
                alert_data[0]["annotations"][annotation_key] = annotation_value
                logger.debug(f"Added custom annotation: '{annotation_key}' = '{annotation_value}'")
        
        if summary:
            alert_data[0]["annotations"]["summary"] = summary
        if description:
            alert_data[0]["annotations"]["description"] = description
        
        logger.debug(f"Initial alert payload created: {json.dumps(alert_data, indent=2)}")
        
        # Prepare headers
        headers = {
            'Content-Type': 'application/json'
        }
        logger.debug(f"Request headers prepared: {headers}")
        
        # Send POST request to Alertmanager
        alertmanager_api_url = f"{ALERTMANAGER_URL}/api/v2/alerts"
        logger.info(f"Sending alert to Alertmanager: {alertmanager_api_url}")
        logger.debug(f"Final alert payload: {json.dumps(alert_data, indent=2)}")
        
        response = requests.post(
            alertmanager_api_url,
            json=alert_data,
            headers=headers,
            timeout=30
        )
        
        logger.debug(f"Received response - Status: {response.status_code}, Response body: {response.text}")
        
        if response.status_code == 200:
            logger.info(f"Alert sent successfully - Summary: '{summary}', Service: '{service}'")
            return True, "Alert sent successfully"
        else:
            logger.error(f"Failed to send alert - HTTP {response.status_code}: {response.text}")
            return False, f"Failed to send alert: HTTP {response.status_code} - {response.text}"
            
    except requests.exceptions.Timeout:
        logger.error(f"Timeout while sending alert to {ALERTMANAGER_URL}")
        return False, "Timeout while sending alert"
    except requests.exceptions.ConnectionError:
        logger.error(f"Connection error - Cannot connect to Alertmanager at {ALERTMANAGER_URL}")
        return False, f"Connection error. Cannot connect to Alertmanager at {ALERTMANAGER_URL}"
    except Exception as e:
        logger.error(f"Unexpected error sending alert: {str(e)}", exc_info=True)
        return False, f"Error sending alert: {str(e)}"

def send_resolved_alert_with_curl(alertname, summary, description, severity, service, custom_labels, custom_annotations):
    """Send resolved alert using curl command to Alertmanager API"""
    logger.debug(f"Starting resolved alert sending process - Summary: '{summary}', Severity: '{severity}', Service: '{service}'")
    
    try:
        # Generate ISO8601 timestamps
        now = datetime.now(timezone.utc)
        starts_at = (now - timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        ends_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        logger.debug(f"Generated resolved alert timestamps - Now: {now}, StartsAt: {starts_at}, EndsAt: {ends_at}")
        
        # Prepare the resolved alert payload
        alert_data = [
            {
                "labels": {
                    "alertname": alertname or "Alert",
                    "severity": severity,
                    "service": service or "unknown"
                },
                "annotations": {},
                "startsAt": starts_at,
                "endsAt": ends_at
            }
        ]
        
        # Add custom labels
        for label_key, label_value in custom_labels.items():
            if label_key and label_value:
                alert_data[0]["labels"][label_key] = label_value
                logger.debug(f"Added custom label to resolved alert: '{label_key}' = '{label_value}'")
        
        # Add custom annotations (only if they have values)
        for annotation_key, annotation_value in custom_annotations.items():
            if annotation_key and annotation_value:
                alert_data[0]["annotations"][annotation_key] = annotation_value
                logger.debug(f"Added custom annotation to resolved alert: '{annotation_key}' = '{annotation_value}'")
        
        if summary:
            alert_data[0]["annotations"]["summary"] = summary
        if description:
            alert_data[0]["annotations"]["description"] = description
        
        logger.debug(f"Initial resolved alert payload created: {json.dumps(alert_data, indent=2)}")
        
        # Prepare headers
        headers = {
            'Content-Type': 'application/json'
        }
        logger.debug(f"Request headers prepared: {headers}")
        
        # Send POST request to Alertmanager
        alertmanager_api_url = f"{ALERTMANAGER_URL}/api/v2/alerts"
        logger.info(f"Sending resolved alert to Alertmanager: {alertmanager_api_url}")
        logger.debug(f"Final resolved alert payload: {json.dumps(alert_data, indent=2)}")
        
        response = requests.post(
            alertmanager_api_url,
            json=alert_data,
            headers=headers,
            timeout=30
        )
        
        logger.debug(f"Received response for resolved alert - Status: {response.status_code}, Response body: {response.text}")
        
        if response.status_code == 200:
            logger.info(f"Resolved alert sent successfully - Summary: '{summary}', Service: '{service}'")
            return True, "Resolved alert sent successfully"
        else:
            logger.error(f"Failed to send resolved alert - HTTP {response.status_code}: {response.text}")
            return False, f"Failed to send resolved alert: HTTP {response.status_code} - {response.text}"
            
    except requests.exceptions.Timeout:
        logger.error(f"Timeout while sending resolved alert to {ALERTMANAGER_URL}")
        return False, "Timeout while sending resolved alert"
    except requests.exceptions.ConnectionError:
        logger.error(f"Connection error - Cannot connect to Alertmanager at {ALERTMANAGER_URL}")
        return False, f"Connection error. Cannot connect to Alertmanager at {ALERTMANAGER_URL}"
    except Exception as e:
        logger.error(f"Unexpected error sending resolved alert: {str(e)}", exc_info=True)
        return False, f"Error sending resolved alert: {str(e)}"

async def auto_resolve_alert(duration_str, summary, description, severity, service, custom_labels, custom_annotations, alert_id=None):
    """Automatically resolve alert after specified duration"""
    logger.debug(f"Starting auto-resolve task for alert: '{summary}' with duration: '{duration_str}'")
    
    try:
        # Parse duration string to seconds
        duration_seconds = parse_duration_to_seconds(duration_str)
        logger.debug(f"Parsed duration '{duration_str}' to {duration_seconds} seconds for alert: '{summary}'")
        
        # Wait for the specified duration
        logger.debug(f"Waiting {duration_seconds} seconds before auto-resolving alert: '{summary}'")
        await asyncio.sleep(duration_seconds)
        
        logger.info(f"Auto-resolving alert: '{summary}' after {duration_str} timeout")
        
        # Send resolved alert
        success, message = send_resolved_alert_with_curl(
            alertname, summary, description, severity, service, custom_labels, custom_annotations
        )
        
        if success:
            logger.info(f"Successfully auto-resolved alert: '{summary}' (Service: '{service}')")
            
            # If alert_id is provided, update status and remove the alert file
            if alert_id:
                # Update alert status to resolved
                resolved_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                update_alert_status(alert_id, 'resolved', resolved_at)
                
                # Broadcast update via WebSocket
                if alert_id in alerts_storage:
                    alert = alerts_storage[alert_id]
                    alert['status'] = 'resolved'
                    alert['resolved_at'] = resolved_at
                    await manager.broadcast({
                        "type": "alert_resolved",
                        "data": alert
                    })
        else:
            logger.error(f"Failed to auto-resolve alert: '{summary}' - {message}")
            
    except Exception as e:
        logger.error(f"Error in auto-resolve task for alert '{summary}': {str(e)}", exc_info=True)

def parse_duration_to_seconds(duration_str):
    """Parse duration string (e.g., '10s', '1m', '5m', '1h') to seconds"""
    logger.debug(f"Parsing duration string: '{duration_str}'")
    
    if duration_str.endswith('s'):
        seconds = int(duration_str[:-1])
        logger.debug(f"Parsed '{duration_str}' as {seconds} seconds")
        return seconds
    elif duration_str.endswith('m'):
        seconds = int(duration_str[:-1]) * 60
        logger.debug(f"Parsed '{duration_str}' as {seconds} seconds ({duration_str[:-1]} minutes)")
        return seconds
    elif duration_str.endswith('h'):
        seconds = int(duration_str[:-1]) * 3600
        logger.debug(f"Parsed '{duration_str}' as {seconds} seconds ({duration_str[:-1]} hours)")
        return seconds
    else:
        # Default to 5 minutes if format is unknown
        logger.warning(f"Unknown duration format '{duration_str}', defaulting to 5 minutes (300 seconds)")
        return 300

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time alert updates"""
    logger.info(f"WebSocket connection attempt from {websocket.client}")
    try:
        await manager.connect(websocket)
        logger.info("WebSocket client connected")
        
        alerts = load_sent_alerts()
        alerts_with_status = []
        
        for alert in alerts:
            alert_info = alert.copy()
            sent_at_str = alert.get('sent_at')
            duration_str = alert.get('duration', '5m')
            
            if sent_at_str and alert.get('status') == 'active':
                try:
                    sent_at = datetime.fromisoformat(sent_at_str.replace('Z', '+00:00'))
                    duration_seconds = parse_duration_to_seconds(duration_str)
                    resolve_at = sent_at + timedelta(seconds=duration_seconds)
                    alert_info['resolve_at'] = resolve_at.isoformat()
                    alert_info['resolve_in_seconds'] = int((resolve_at - datetime.now(timezone.utc)).total_seconds())
                    alert_info['resolve_timestamp'] = int(resolve_at.timestamp())
                except Exception as e:
                    logger.warning(f"Failed to calculate resolve time for alert {alert.get('id')}: {e}")
            
            alerts_with_status.append(alert_info)
        
        await websocket.send_json({
            "type": "initial_data",
            "data": alerts_with_status
        })
        
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        manager.disconnect(websocket)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main page with unified table interface"""
    alerts = load_sent_alerts()
    alerts_with_status = []
    
    for alert in alerts:
        alert_info = alert.copy()
        sent_at_str = alert.get('sent_at')
        duration_str = alert.get('duration', '5m')
        
        if sent_at_str and alert.get('status') == 'active':
            try:
                sent_at = datetime.fromisoformat(sent_at_str.replace('Z', '+00:00'))
                duration_seconds = parse_duration_to_seconds(duration_str)
                resolve_at = sent_at + timedelta(seconds=duration_seconds)
                alert_info['resolve_at'] = resolve_at.isoformat()
                alert_info['resolve_in_seconds'] = int((resolve_at - datetime.now(timezone.utc)).total_seconds())
                alert_info['resolve_timestamp'] = int(resolve_at.timestamp())
            except Exception as e:
                logger.warning(f"Failed to calculate resolve time for alert {alert.get('id')}: {e}")
        
        alerts_with_status.append(alert_info)
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "alerts": alerts_with_status
    })

@app.post("/api/alerts/create")
async def create_alert_api(
    request: Request
):
    """API endpoint to create alert from JSON"""
    try:
        data = await request.json()
        alertname = data.get('alertname', '').strip()
        summary = data.get('summary', '').strip()
        description = data.get('description', '').strip()
        severity = data.get('severity', '').strip()
        duration = data.get('duration', '').strip()
        service = data.get('service', '').strip()
        custom_labels = data.get('custom_labels', {})
        custom_annotations = data.get('custom_annotations', {})
        client_row_id = data.get('client_row_id')
        
        if not duration:
            return {"success": False, "message": "Duration is required field"}
        
        if not severity:
            severity = 'default'
        
        if severity not in ['default', 'info', 'warning', 'critical']:
            return {"success": False, "message": "Invalid severity level"}
        
        success, message = send_alert_with_curl(
            alertname, summary, description, severity, duration, service, custom_labels, custom_annotations
        )
        
        if success:
            alert_id = str(uuid.uuid4())
            sent_at_dt = datetime.now(timezone.utc)
            sent_at = sent_at_dt.isoformat().replace("+00:00", "Z")
            
            try:
                sent_at_dt = datetime.fromisoformat(sent_at.replace('Z', '+00:00'))
                duration_seconds = parse_duration_to_seconds(duration)
                resolve_at = sent_at_dt + timedelta(seconds=duration_seconds)
                resolve_at_iso = resolve_at.isoformat()
                resolve_in_seconds = int((resolve_at - datetime.now(timezone.utc)).total_seconds())
                resolve_timestamp = int(resolve_at.timestamp())
            except Exception as e:
                logger.warning(f"Failed to calculate resolve time: {e}")
                resolve_at_iso = None
                resolve_in_seconds = None
                resolve_timestamp = None
            
            alert_info = {
                'id': alert_id,
                'alertname': alertname,
                'summary': summary,
                'description': description,
                'severity': severity,
                'service': service,
                'duration': duration,
                'custom_labels': custom_labels,
                'custom_annotations': custom_annotations,
                'sent_at': sent_at,
                'status': 'active',
                'auto_resolve_scheduled': True,
                'resolve_at': resolve_at_iso,
                'resolve_in_seconds': resolve_in_seconds,
                'resolve_timestamp': resolve_timestamp,
                'client_row_id': client_row_id
            }
            
            logger.info(f"Creating alert with status='active', resolve_timestamp={resolve_timestamp}, duration={duration}")
            
            add_sent_alert(alert_info)
            
            await manager.broadcast({
                "type": "alert_added",
                "data": alert_info
            })
            
            asyncio.create_task(auto_resolve_alert(
                duration, summary, description, severity, service, custom_labels, custom_annotations, alert_id
            ))
            
            return {"success": True, "message": message, "alert": alert_info}
        else:
            return {"success": False, "message": message}
    except Exception as e:
        logger.error(f"Error creating alert: {e}", exc_info=True)
        return {"success": False, "message": f"Error: {str(e)}"}

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
    logger.info(f"Received alert form submission - Summary: '{summary}', Severity: '{severity}', Service: '{service}', Duration: '{duration}'")
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
    
    # Validate required fields (only duration is required now)
    logger.debug(f"Validating form fields - Summary: '{summary.strip()}', Description: '{description.strip()}', Severity: '{severity.strip()}', Duration: '{duration.strip()}', Service: '{service.strip()}'")
    if not duration.strip():
        logger.warning("Form validation failed - duration field is empty")
        return templates.TemplateResponse("index.html", {
            "request": request,
            "history": history,
            "message": "Duration is required field",
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
    
    if not severity.strip():
        severity = 'default'
    else:
        severity = severity.strip()
    
    if severity not in ['default', 'info', 'warning', 'critical']:
        logger.warning(f"Form validation failed - invalid severity level: '{severity}'")
        return templates.TemplateResponse("index.html", {
            "request": request,
            "history": history,
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
    
    logger.info(f"Form validation passed. Sending alert: '{summary.strip()}' to Alertmanager")
    
    # Send alert using curl
    success, message = send_alert_with_curl(
        summary.strip(),
        summary.strip(),
        description.strip(),
        severity.strip(),
        duration.strip(),
        service.strip(),
        custom_labels,
        custom_annotations
    )
    
    if success:
        # Generate unique alert ID
        alert_id = str(uuid.uuid4())
        
        # Save alert info for later resolve
        sent_at_dt = datetime.now(timezone.utc)
        sent_at = sent_at_dt.isoformat().replace("+00:00", "Z")
        alert_info = {
            'id': alert_id,
            'summary': summary.strip(),
            'description': description.strip(),
            'severity': severity.strip(),
            'service': service.strip(),
            'duration': duration.strip(),
            'custom_labels': custom_labels,
            'custom_annotations': custom_annotations,
            'sent_at': sent_at,
            'status': 'active',
            'auto_resolve_scheduled': True
        }
        add_sent_alert(alert_info)
        
        # Calculate resolve time for WebSocket broadcast
        try:
            sent_at_dt = datetime.fromisoformat(sent_at.replace('Z', '+00:00'))
            duration_seconds = parse_duration_to_seconds(duration.strip())
            resolve_at = sent_at_dt + timedelta(seconds=duration_seconds)
            alert_info['resolve_at'] = resolve_at.isoformat()
            alert_info['resolve_in_seconds'] = int((resolve_at - datetime.now(timezone.utc)).total_seconds())
            alert_info['resolve_timestamp'] = int(resolve_at.timestamp())
        except Exception as e:
            logger.warning(f"Failed to calculate resolve time: {e}")
        
        # Broadcast new alert via WebSocket
        await manager.broadcast({
            "type": "alert_added",
            "data": alert_info
        })
        
        # Start auto-resolve task
        logger.info(f"Created auto-resolve task for alert: '{summary.strip()}' with duration: {duration.strip()}")
        asyncio.create_task(auto_resolve_alert(
            duration.strip(),
            summary.strip(),
            description.strip(),
            severity.strip(),
            service.strip(),
            custom_labels,
            custom_annotations,
            alert_id
        ))
        
        # Update history
        add_to_history(history, 'summaries', summary.strip())
        add_to_history(history, 'descriptions', description.strip())
        add_to_history(history, 'services', service.strip())
        add_to_history(history, 'severities', severity.strip())
        add_to_history(history, 'durations', duration.strip())
        save_form_history(history)
        
        return RedirectResponse(url="/", status_code=303)
    else:
        alerts = load_sent_alerts()
        alerts_with_status = []
        
        for alert in alerts:
            alert_info = alert.copy()
            sent_at_str = alert.get('sent_at')
            duration_str = alert.get('duration', '5m')
            
            if sent_at_str and alert.get('status') == 'active':
                try:
                    sent_at = datetime.fromisoformat(sent_at_str.replace('Z', '+00:00'))
                    duration_seconds = parse_duration_to_seconds(duration_str)
                    resolve_at = sent_at + timedelta(seconds=duration_seconds)
                    alert_info['resolve_at'] = resolve_at.isoformat()
                    alert_info['resolve_in_seconds'] = int((resolve_at - datetime.now(timezone.utc)).total_seconds())
                    alert_info['resolve_timestamp'] = int(resolve_at.timestamp())
                except Exception as e:
                    logger.warning(f"Failed to calculate resolve time for alert {alert.get('id')}: {e}")
            
            alerts_with_status.append(alert_info)
        
        return templates.TemplateResponse("index.html", {
            "request": request,
            "alerts": alerts_with_status,
            "error_message": message
        })

def load_sent_alerts():
    """Load all sent alerts from in-memory storage"""
    alerts = list(alerts_storage.values())
    logger.debug(f"Loaded {len(alerts)} alerts from memory")
    return alerts

def save_alert_to_file(alert_info):
    """Save individual alert to a JSON file in alerts directory"""
    alert_id = alert_info.get('id', 'unknown')
    filename = f"{alert_id}.json"
    filepath = os.path.join(ALERTS_DIR, filename)
    
    try:
        with open(filepath, 'w') as f:
            json.dump(alert_info, f, indent=2)
        logger.debug(f"Alert saved to file: {filepath}")
        return True
    except Exception as e:
        logger.error(f"Failed to save alert to file {filepath}: {e}")
        return False

def remove_alert_file(alert_id):
    """Remove alert file from alerts directory"""
    filename = f"{alert_id}.json"
    filepath = os.path.join(ALERTS_DIR, filename)
    
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            logger.info(f"Alert file removed: {filepath}")
            if os.path.exists(filepath):
                logger.error(f"Alert file still exists after removal attempt: {filepath}")
                return False
            return True
        else:
            logger.debug(f"Alert file not found (may have been already deleted): {filepath}")
            return True
    except Exception as e:
        logger.error(f"Failed to remove alert file {filepath}: {e}", exc_info=True)
        return False

def update_alert_status(alert_id, status, resolved_at=None):
    """Update alert status in memory storage"""
    try:
        if alert_id in alerts_storage:
            alerts_storage[alert_id]['status'] = status
            if resolved_at:
                alerts_storage[alert_id]['resolved_at'] = resolved_at
            save_alert_to_file(alerts_storage[alert_id])
            logger.debug(f"Updated alert status to '{status}' for alert: {alert_id}")
            return True
        else:
            logger.warning(f"Alert not found in memory for status update: {alert_id}")
            return False
    except Exception as e:
        logger.error(f"Failed to update alert status for {alert_id}: {e}")
        return False

def add_sent_alert(alert_info):
    """Add alert to in-memory storage"""
    alert_id = alert_info.get('id', 'unknown')
    logger.debug(f"Adding alert to memory: '{alert_info.get('summary', 'Unknown')}' (ID: {alert_id})")
    alerts_storage[alert_id] = alert_info
    save_alert_to_file(alert_info)
    logger.debug(f"Alert added successfully to memory storage")
    return True

def get_sent_alerts():
    """Get all sent alerts"""
    return load_sent_alerts()

async def resolve_sent_alert(alert_id):
    """Resolve a specific sent alert"""
    logger.info(f"Attempting to resolve alert with ID: {alert_id}")
    alerts = load_sent_alerts()
    logger.debug(f"Loaded {len(alerts)} sent alerts for resolution lookup")
    
    for alert in alerts:
        if alert.get('id') == alert_id:
            logger.info(f"Found alert to resolve: '{alert.get('summary', 'Unknown')}' (Service: {alert.get('service', 'Unknown')})")
            # Send resolved alert
            success, message = send_resolved_alert_with_curl(
                alert.get('alertname') or alert.get('summary', ''),
                alert.get('custom_annotations', {}).get('summary') or alert.get('summary', ''),
                alert['description'],
                alert['severity'],
                alert['service'],
                alert.get('custom_labels', {}),
                alert.get('custom_annotations', {})
            )
            if success:
                # Update status
                resolved_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                update_alert_status(alert_id, 'resolved', resolved_at)
                
                # Broadcast update
                if alert_id in alerts_storage:
                    alert = alerts_storage[alert_id]
                    alert['status'] = 'resolved'
                    alert['resolved_at'] = resolved_at
                    await manager.broadcast({
                        "type": "alert_resolved",
                        "data": alert
                    })
                
                logger.info(f"Successfully resolved alert '{alert.get('summary', 'Unknown')}'")
                return True, "Alert resolved successfully"
            else:
                logger.error(f"Failed to resolve alert '{alert.get('summary', 'Unknown')}': {message}")
                return False, message
    
def close_all_alerts():
    """Close all active alerts by sending resolved alerts and removing files"""
    logger.info("Starting to close all active alerts")
    alerts = load_sent_alerts()
    closed_count = 0
    errors = []
    
    for alert in alerts:
        alert_id = alert.get('id')
        alert_summary = alert.get('summary', 'Unknown')
        
        logger.debug(f"Closing alert: '{alert_summary}' (ID: {alert_id})")
        
        # Send resolved alert
        success, message = send_resolved_alert_with_curl(
            alert['summary'],
            alert['description'],
            alert['severity'],
            alert['service'],
            alert.get('custom_labels', {}),
            alert.get('custom_annotations', {})
        )
        
        if success:
            # Remove alert file
            file_removed = remove_alert_file(alert_id)
            if file_removed:
                closed_count += 1
                logger.info(f"Successfully closed alert: '{alert_summary}'")
            else:
                errors.append(f"Alert '{alert_summary}' resolved but file removal failed")
        else:
            errors.append(f"Failed to resolve alert '{alert_summary}': {message}")
    
    logger.info(f"Closed {closed_count}/{len(alerts)} alerts. Errors: {len(errors)}")
    if errors:
        logger.warning(f"Errors during bulk close: {errors}")
    
    return closed_count, errors

def cleanup_old_alerts(days_old=7):
    """Remove alert files older than specified days"""
    logger.info(f"Starting cleanup of alerts older than {days_old} days")
    cutoff_time = datetime.now(timezone.utc) - timedelta(days=days_old)
    removed_count = 0
    
    try:
        if os.path.exists(ALERTS_DIR):
            for filename in os.listdir(ALERTS_DIR):
                if filename.endswith('.json'):
                    filepath = os.path.join(ALERTS_DIR, filename)
                    try:
                        # Check file modification time
                        file_mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                        if file_mtime < cutoff_time:
                            os.remove(filepath)
                            removed_count += 1
                            logger.debug(f"Removed old alert file: {filename}")
                    except Exception as e:
                        logger.warning(f"Failed to process file {filename}: {e}")
        
        logger.info(f"Cleanup completed. Removed {removed_count} old alert files")
        return removed_count
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        return 0


@app.post("/resolve-alert/{alert_id}")
async def resolve_alert_endpoint(alert_id: str):
    """Resolve a specific alert"""
    success, message = await resolve_sent_alert(alert_id)
    return {"success": success, "message": message}

@app.post("/toggle-alert-status/{alert_id}")
async def toggle_alert_status_endpoint(alert_id: str):
    """Toggle alert status between firing and resolved"""
    logger.info(f"Toggling alert status for ID: {alert_id}")
    alerts = load_sent_alerts()
    
    for alert in alerts:
        if alert.get('id') == alert_id:
            current_status = alert.get('status', 'active')
            new_status = 'resolved' if current_status == 'active' else 'active'
            
            if new_status == 'resolved':
                success, message = send_resolved_alert_with_curl(
                    alert.get('alertname') or alert.get('summary', ''),
                    alert.get('custom_annotations', {}).get('summary') or alert.get('summary', ''),
                    alert['description'],
                    alert['severity'],
                    alert['service'],
                    alert.get('custom_labels', {}),
                    alert.get('custom_annotations', {})
                )
                if not success:
                    return {"success": False, "message": message}
                
                resolved_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                update_alert_status(alert_id, 'resolved', resolved_at)
                alert['status'] = 'resolved'
                alert['resolved_at'] = resolved_at
            else:
                success, message = send_alert_with_curl(
                    alert.get('alertname') or alert.get('summary', ''),
                    alert.get('custom_annotations', {}).get('summary') or alert.get('summary', ''),
                    alert['description'],
                    alert['severity'],
                    alert.get('duration', '5m'),
                    alert['service'],
                    alert.get('custom_labels', {}),
                    alert.get('custom_annotations', {})
                )
                if not success:
                    return {"success": False, "message": message}
                
                sent_at_dt = datetime.now(timezone.utc)
                sent_at = sent_at_dt.isoformat().replace("+00:00", "Z")
                alert['status'] = 'active'
                alert['sent_at'] = sent_at
                if 'resolved_at' in alert:
                    del alert['resolved_at']
                
                try:
                    sent_at_dt = datetime.fromisoformat(sent_at.replace('Z', '+00:00'))
                    duration_seconds = parse_duration_to_seconds(alert.get('duration', '5m'))
                    resolve_at = sent_at_dt + timedelta(seconds=duration_seconds)
                    alert['resolve_at'] = resolve_at.isoformat()
                    alert['resolve_in_seconds'] = int((resolve_at - datetime.now(timezone.utc)).total_seconds())
                    alert['resolve_timestamp'] = int(resolve_at.timestamp())
                except Exception as e:
                    logger.warning(f"Failed to calculate resolve time: {e}")
                
                if alert_id in alerts_storage:
                    alerts_storage[alert_id].update(alert)
                    save_alert_to_file(alerts_storage[alert_id])
                else:
                    alerts_storage[alert_id] = alert
                    save_alert_to_file(alert)
                
                asyncio.create_task(auto_resolve_alert(
                    alert.get('duration', '5m'),
                    alert['summary'],
                    alert['description'],
                    alert['severity'],
                    alert['service'],
                    alert.get('custom_labels', {}),
                    alert.get('custom_annotations', {}),
                    alert_id
                ))
            
            await manager.broadcast({
                "type": "alert_update",
                "data": alert
            })
            
            return {"success": True, "message": f"Alert status changed to {new_status}", "status": new_status}
    
    return {"success": False, "message": "Alert not found"}

@app.post("/close-all-alerts")
async def close_all_alerts_endpoint():
    """Close all active alerts"""
    closed_count, errors = close_all_alerts()
    return {
        "success": len(errors) == 0,
        "closed_count": closed_count,
        "errors": errors,
        "message": f"Closed {closed_count} alerts" + (f". Errors: {len(errors)}" if errors else "")
    }

@app.post("/cleanup-old-alerts")
async def cleanup_old_alerts_endpoint(days_old: int = 7):
    """Cleanup alert files older than specified days"""
    removed_count = cleanup_old_alerts(days_old)
    return {
        "success": True,
        "removed_count": removed_count,
        "message": f"Removed {removed_count} old alert files"
    }

@app.post("/update-alert-duration/{alert_id}")
async def update_alert_duration_endpoint(alert_id: str, request: Request):
    """Update alert duration and recalculate resolve time"""
    try:
        data = await request.json()
        new_duration = data.get('duration', '5m')
        
        if alert_id in alerts_storage:
            alert = alerts_storage[alert_id]
            if alert.get('status') == 'active':
                alert['duration'] = new_duration
                
                sent_at_str = alert.get('sent_at')
                if sent_at_str:
                    try:
                        sent_at = datetime.fromisoformat(sent_at_str.replace('Z', '+00:00'))
                        duration_seconds = parse_duration_to_seconds(new_duration)
                        resolve_at = sent_at + timedelta(seconds=duration_seconds)
                        alert['resolve_at'] = resolve_at.isoformat()
                        alert['resolve_in_seconds'] = int((resolve_at - datetime.now(timezone.utc)).total_seconds())
                        alert['resolve_timestamp'] = int(resolve_at.timestamp())
                    except Exception as e:
                        logger.warning(f"Failed to calculate resolve time: {e}")
                
                save_alert_to_file(alert)
                
                await manager.broadcast({
                    "type": "alert_update",
                    "data": alert
                })
                
                return {"success": True, "message": "Duration updated", "alert": alert}
            else:
                return {"success": False, "message": "Can only update duration for active alerts"}
        else:
            return {"success": False, "message": "Alert not found"}
    except Exception as e:
        logger.error(f"Error updating alert duration: {e}", exc_info=True)
        return {"success": False, "message": f"Error: {str(e)}"}

@app.post("/api/alerts/update/{alert_id}")
async def update_alert_endpoint(alert_id: str, request: Request):
    """Update existing resolved alert and resend it as active"""
    try:
        data = await request.json()
        alertname = data.get('alertname', '').strip()
        summary = data.get('summary', '').strip()
        description = data.get('description', '').strip()
        severity = data.get('severity', '').strip()
        duration = data.get('duration', '').strip()
        service = data.get('service', '').strip()
        custom_labels = data.get('custom_labels', {})
        custom_annotations = data.get('custom_annotations', {})
        client_row_id = data.get('client_row_id')
        
        if not duration:
            return {"success": False, "message": "Duration is required field"}
        
        if not severity:
            severity = 'default'
        
        if severity not in ['default', 'info', 'warning', 'critical']:
            return {"success": False, "message": "Invalid severity level"}
        
        if alert_id not in alerts_storage:
            return {"success": False, "message": "Alert not found"}
        
        success, message = send_alert_with_curl(
            alertname, summary, description, severity, duration, service, custom_labels, custom_annotations
        )
        
        if success:
            sent_at_dt = datetime.now(timezone.utc)
            sent_at = sent_at_dt.isoformat().replace("+00:00", "Z")
            
            try:
                sent_at_dt = datetime.fromisoformat(sent_at.replace('Z', '+00:00'))
                duration_seconds = parse_duration_to_seconds(duration)
                resolve_at = sent_at_dt + timedelta(seconds=duration_seconds)
                resolve_at_iso = resolve_at.isoformat()
                resolve_in_seconds = int((resolve_at - datetime.now(timezone.utc)).total_seconds())
                resolve_timestamp = int(resolve_at.timestamp())
            except Exception as e:
                logger.warning(f"Failed to calculate resolve time: {e}")
                resolve_at_iso = None
                resolve_in_seconds = None
                resolve_timestamp = None
            
            alert_info = alerts_storage[alert_id]
            alert_info.update({
                'summary': summary,
                'description': description,
                'severity': severity,
                'service': service,
                'duration': duration,
                'custom_labels': custom_labels,
                'custom_annotations': custom_annotations,
                'sent_at': sent_at,
                'status': 'active',
                'auto_resolve_scheduled': True,
                'resolve_at': resolve_at_iso,
                'resolve_in_seconds': resolve_in_seconds,
                'resolve_timestamp': resolve_timestamp,
                'client_row_id': client_row_id
            })
            
            if 'resolved_at' in alert_info:
                del alert_info['resolved_at']
            
            save_alert_to_file(alert_info)
            
            asyncio.create_task(auto_resolve_alert(
                duration, summary, description, severity, service, custom_labels, custom_annotations, alert_id
            ))
            
            await manager.broadcast({
                "type": "alert_update",
                "data": alert_info
            })
            
            logger.info(f"Alert updated and resent: {alert_id}")
            return {"success": True, "message": "Alert updated and sent", "alert": alert_info}
        else:
            return {"success": False, "message": message}
    except Exception as e:
        logger.error(f"Error updating alert: {e}", exc_info=True)
        return {"success": False, "message": f"Error: {str(e)}"}

@app.post("/delete-alert/{alert_id}")
async def delete_alert_endpoint(alert_id: str):
    """Delete alert from memory and file system"""
    try:
        if alert_id in alerts_storage:
            alert = alerts_storage[alert_id]
            logger.info(f"Deleting alert: {alert_id} - {alert.get('summary', 'Unknown')}")
            
            del alerts_storage[alert_id]
            logger.debug(f"Alert removed from memory: {alert_id}")
            
            file_removed = remove_alert_file(alert_id)
            if file_removed:
                logger.debug(f"Alert file removed: {alert_id}")
            else:
                logger.warning(f"Alert file not found or failed to remove: {alert_id}")
            
            await manager.broadcast({
                "type": "alert_removed",
                "data": {"id": alert_id}
            })
            
            logger.info(f"Alert deleted successfully: {alert_id}")
            return {"success": True, "message": "Alert deleted"}
        else:
            logger.warning(f"Alert not found in memory: {alert_id}")
            file_removed = remove_alert_file(alert_id)
            if file_removed:
                logger.info(f"Alert file removed even though not in memory: {alert_id}")
                return {"success": True, "message": "Alert file deleted"}
            return {"success": False, "message": "Alert not found"}
    except Exception as e:
        logger.error(f"Error deleting alert: {e}", exc_info=True)
        return {"success": False, "message": f"Error: {str(e)}"}

@app.get("/alerts/status")
async def alerts_status():
    """Get status of all alerts"""
    alerts = load_sent_alerts()
    return {
        "total_alerts": len(alerts),
        "alerts": alerts,
        "alerts_directory": ALERTS_DIR
    }

@app.get("/test-ws")
async def test_ws():
    """Test endpoint to verify WebSocket route exists"""
    return {"message": "WebSocket endpoint should be at /ws", "routes": [str(route) for route in app.routes if hasattr(route, 'path')]}

@app.get("/api/alerts")
async def get_alerts_api():
    """Get active alerts with calculated resolve time"""
    alerts = load_sent_alerts()
    alerts_with_resolve_time = []
    
    for alert in alerts:
        if alert.get('status') == 'active':
            # Calculate resolve time
            sent_at_str = alert.get('sent_at')
            duration_str = alert.get('duration', '5m')
            
            if sent_at_str:
                try:
                    sent_at = datetime.fromisoformat(sent_at_str.replace('Z', '+00:00'))
                    duration_seconds = parse_duration_to_seconds(duration_str)
                    resolve_at = sent_at + timedelta(seconds=duration_seconds)
                    
                    alert_info = alert.copy()
                    alert_info['resolve_at'] = resolve_at.isoformat()
                    alert_info['resolve_in_seconds'] = int((resolve_at - datetime.now(timezone.utc)).total_seconds())
                    alerts_with_resolve_time.append(alert_info)
                except Exception as e:
                    logger.warning(f"Failed to calculate resolve time for alert {alert.get('id')}: {e}")
    
    return {
        "active_alerts": alerts_with_resolve_time,
        "total_active": len(alerts_with_resolve_time)
    }

def load_alerts_from_files():
    """Load existing alerts from files into memory on startup"""
    try:
        if os.path.exists(ALERTS_DIR):
            for filename in os.listdir(ALERTS_DIR):
                if filename.endswith('.json'):
                    filepath = os.path.join(ALERTS_DIR, filename)
                    try:
                        with open(filepath, 'r') as f:
                            alert_data = json.load(f)
                            alert_id = alert_data.get('id')
                            if alert_id:
                                alerts_storage[alert_id] = alert_data
                    except Exception as e:
                        logger.warning(f"Failed to load alert file {filename}: {e}")
        logger.info(f"Loaded {len(alerts_storage)} alerts from files into memory")
    except Exception as e:
        logger.error(f"Error loading alerts from files: {e}")

if __name__ == "__main__":
    load_alerts_from_files()
    port = int(os.environ.get("ADAM_PORT", 5067))
    logger.info(f"Starting server on 0.0.0.0:{port}")
    logger.info(f"WebSocket endpoint available at ws://0.0.0.0:{port}/ws")
    try:
        uvicorn.run(app, host="0.0.0.0", port=port, ws="websockets")
    except Exception as e:
        logger.warning(f"Failed to use websockets backend, trying auto: {e}")
        uvicorn.run(app, host="0.0.0.0", port=port, ws="auto")
