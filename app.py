from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import json
import os
import asyncio
import uuid
import logging
from datetime import datetime, timedelta
from typing import List, Optional
import uvicorn
import requests
from dotenv import load_dotenv

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
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
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
    logger.debug(f"Starting alert sending process - Summary: '{summary}', Severity: '{severity}', Service: '{service}'")
    
    try:
        # Generate ISO8601 timestamps
        now = datetime.utcnow()
        starts_at = (now - timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        logger.debug(f"Generated timestamps - Now: {now}, StartsAt: {starts_at}")
        
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
        logger.debug(f"Initial alert payload created: {json.dumps(alert_data, indent=2)}")
        
        # Add custom labels
        for label_key, label_value in custom_labels.items():
            if label_key and label_value:
                alert_data[0]["labels"][label_key] = label_value
                logger.debug(f"Added custom label: '{label_key}' = '{label_value}'")
        
        # Add custom annotations
        for annotation_key, annotation_value in custom_annotations.items():
            if annotation_key and annotation_value:
                alert_data[0]["annotations"][annotation_key] = annotation_value
                logger.debug(f"Added custom annotation: '{annotation_key}' = '{annotation_value}'")
        
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

def send_resolved_alert_with_curl(summary, description, severity, service, custom_labels, custom_annotations):
    """Send resolved alert using curl command to Alertmanager API"""
    logger.debug(f"Starting resolved alert sending process - Summary: '{summary}', Severity: '{severity}', Service: '{service}'")
    
    try:
        # Generate ISO8601 timestamps
        now = datetime.utcnow()
        starts_at = (now - timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        ends_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        logger.debug(f"Generated resolved alert timestamps - Now: {now}, StartsAt: {starts_at}, EndsAt: {ends_at}")
        
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
        logger.debug(f"Initial resolved alert payload created: {json.dumps(alert_data, indent=2)}")
        
        # Add custom labels
        for label_key, label_value in custom_labels.items():
            if label_key and label_value:
                alert_data[0]["labels"][label_key] = label_value
                logger.debug(f"Added custom label to resolved alert: '{label_key}' = '{label_value}'")
        
        # Add custom annotations
        for annotation_key, annotation_value in custom_annotations.items():
            if annotation_key and annotation_value:
                alert_data[0]["annotations"][annotation_key] = annotation_value
                logger.debug(f"Added custom annotation to resolved alert: '{annotation_key}' = '{annotation_value}'")
        
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
            summary, description, severity, service, custom_labels, custom_annotations
        )
        
        if success:
            logger.info(f"Successfully auto-resolved alert: '{summary}' (Service: '{service}')")
            
            # If alert_id is provided, update status and remove the alert file
            if alert_id:
                # Update alert status to resolved
                resolved_at = datetime.utcnow().isoformat()
                update_alert_status(alert_id, 'resolved', resolved_at)
                
                # Remove the alert file after a short delay to allow status update
                await asyncio.sleep(1)
                file_removed = remove_alert_file(alert_id)
                if file_removed:
                    logger.info(f"Removed alert file for auto-resolved alert: '{summary}'")
                else:
                    logger.warning(f"Failed to remove alert file for auto-resolved alert: '{summary}'")
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
    
    # Validate required fields
    logger.debug(f"Validating form fields - Summary: '{summary.strip()}', Description: '{description.strip()}', Severity: '{severity.strip()}', Duration: '{duration.strip()}', Service: '{service.strip()}'")
    if not all([summary.strip(), description.strip(), severity.strip(), duration.strip(), service.strip()]):
        logger.warning("Form validation failed - one or more required fields are empty")
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
        logger.warning(f"Form validation failed - invalid severity level: '{severity}'")
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
    
    logger.info(f"Form validation passed. Sending alert: '{summary.strip()}' to Alertmanager")
    
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
        # Generate unique alert ID
        alert_id = str(uuid.uuid4())
        
        # Save alert info for later resolve
        alert_info = {
            'id': alert_id,
            'summary': summary.strip(),
            'description': description.strip(),
            'severity': severity.strip(),
            'service': service.strip(),
            'duration': duration.strip(),
            'custom_labels': custom_labels,
            'custom_annotations': custom_annotations,
            'sent_at': datetime.utcnow().isoformat(),
            'status': 'active',
            'auto_resolve_scheduled': True
        }
        add_sent_alert(alert_info)
        
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

def load_sent_alerts():
    """Load all sent alerts from JSON files in alerts directory"""
    alerts = []
    try:
        if os.path.exists(ALERTS_DIR):
            for filename in os.listdir(ALERTS_DIR):
                if filename.endswith('.json'):
                    filepath = os.path.join(ALERTS_DIR, filename)
                    try:
                        with open(filepath, 'r') as f:
                            alert_data = json.load(f)
                            alerts.append(alert_data)
                    except Exception as e:
                        logger.warning(f"Failed to load alert file {filename}: {e}")
        logger.debug(f"Loaded {len(alerts)} alerts from {ALERTS_DIR} directory")
    except Exception as e:
        logger.error(f"Error loading alerts from directory: {e}")
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
            logger.debug(f"Alert file removed: {filepath}")
            return True
        else:
            logger.warning(f"Alert file not found: {filepath}")
            return False
    except Exception as e:
        logger.error(f"Failed to remove alert file {filepath}: {e}")
        return False

def update_alert_status(alert_id, status, resolved_at=None):
    """Update alert status in the JSON file"""
    filename = f"{alert_id}.json"
    filepath = os.path.join(ALERTS_DIR, filename)
    
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                alert_data = json.load(f)
            
            alert_data['status'] = status
            if resolved_at:
                alert_data['resolved_at'] = resolved_at
            
            with open(filepath, 'w') as f:
                json.dump(alert_data, f, indent=2)
            
            logger.debug(f"Updated alert status to '{status}' for alert: {alert_id}")
            return True
        else:
            logger.warning(f"Alert file not found for status update: {filepath}")
            return False
    except Exception as e:
        logger.error(f"Failed to update alert status for {alert_id}: {e}")
        return False

def add_sent_alert(alert_info):
    """Add alert to sent alerts directory"""
    logger.debug(f"Adding alert to alerts directory: '{alert_info.get('summary', 'Unknown')}' (ID: {alert_info.get('id', 'Unknown')})")
    success = save_alert_to_file(alert_info)
    if success:
        logger.debug(f"Alert added successfully to alerts directory")
    return success

def get_sent_alerts():
    """Get all sent alerts"""
    return load_sent_alerts()

def resolve_sent_alert(alert_id):
    """Resolve a specific sent alert"""
    logger.info(f"Attempting to resolve alert with ID: {alert_id}")
    alerts = load_sent_alerts()
    logger.debug(f"Loaded {len(alerts)} sent alerts for resolution lookup")
    
    for alert in alerts:
        if alert.get('id') == alert_id:
            logger.info(f"Found alert to resolve: '{alert.get('summary', 'Unknown')}' (Service: {alert.get('service', 'Unknown')})")
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
                # Remove alert file from directory
                file_removed = remove_alert_file(alert_id)
                if file_removed:
                    logger.info(f"Successfully resolved and removed alert '{alert.get('summary', 'Unknown')}' from alerts directory")
                    return True, "Alert resolved successfully"
                else:
                    logger.warning(f"Alert resolved but file removal failed for '{alert.get('summary', 'Unknown')}'")
                    return True, "Alert resolved but file cleanup failed"
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
    cutoff_time = datetime.utcnow() - timedelta(days=days_old)
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

@app.get("/bulk-generate", response_class=HTMLResponse)
async def bulk_generate_page(request: Request):
    """Bulk generate alerts page"""
    sent_alerts = get_sent_alerts()
    return templates.TemplateResponse("bulk_generate.html", {
        "request": request,
        "alertmanager_url": ALERTMANAGER_URL,
        "sent_alerts": sent_alerts
    })

@app.post("/bulk-generate", response_class=HTMLResponse)
async def bulk_generate_alerts(
    request: Request,
    count: int = Form(10),
    duration: str = Form("5m")
):
    """Generate multiple random alerts"""
    logger.info(f"Starting bulk generate alerts - Count: {count}, Duration: {duration}")
    import random
    
    # Random words for summaries and descriptions
    summary_nouns = [
        "Database", "Connection", "Memory", "CPU", "Disk", "Network", "Service", "API", "Cache", "Queue",
        "Timeout", "Error", "Failure", "Warning", "Critical", "Overflow", "Underflow", "Server", "Client", "Process"
    ]
    
    summary_adjectives = [
        "High", "Low", "Critical", "Warning", "Error", "Failed", "Slow", "Fast", "Overloaded", "Underutilized",
        "Broken", "Unstable", "Degraded", "Unavailable", "Responsive", "Unresponsive", "Healthy", "Unhealthy"
    ]
    
    description_words = [
        "is experiencing issues", "has high latency", "is running out of resources", "is not responding",
        "has exceeded threshold", "is down", "is slow", "is overloaded", "has errors", "needs attention",
        "requires maintenance", "is unstable", "has performance problems", "is failing", "is degraded"
    ]
    
    # Random service names
    service_names = [
        "auth-service", "api-gateway", "user-service", "payment-service", "notification-service",
        "database-service", "cache-service", "queue-service", "storage-service", "monitoring-service",
        "frontend-app", "backend-api", "mobile-api", "admin-panel", "analytics-service",
        "search-service", "email-service", "sms-service", "file-service", "log-service"
    ]
    
    severities = ["info", "warning", "critical"]
    logger.debug(f"Generated random data pools - Nouns: {len(summary_nouns)}, Adjectives: {len(summary_adjectives)}, Descriptions: {len(description_words)}, Services: {len(service_names)}")
    
    generated_count = 0
    errors = []
    
    logger.info(f"Starting generation loop for {count} alerts")
    
    for i in range(count):
        try:
            # Generate random alert data
            summary = f"{random.choice(summary_nouns)}{random.choice(summary_adjectives)}"
            description = f"{summary} {random.choice(description_words)}"
            severity = random.choice(severities)
            service = random.choice(service_names)
            
            logger.debug(f"Generated alert #{i+1}: '{summary}' (Severity: {severity}, Service: {service})")
            
            # Send alert
            success, message = send_alert_with_curl(
                summary, description, severity, duration, service, {}, {}
            )
            
            if success:
                # Generate unique alert ID
                alert_id = str(uuid.uuid4())
                logger.debug(f"Generated alert ID: {alert_id} for alert: '{summary}'")
                
                # Save alert info
                alert_info = {
                    'id': alert_id,
                    'summary': summary,
                    'description': description,
                    'severity': severity,
                    'service': service,
                    'duration': duration,
                    'custom_labels': {},
                    'custom_annotations': {},
                    'sent_at': datetime.utcnow().isoformat(),
                    'status': 'active',
                    'auto_resolve_scheduled': True
                }
                add_sent_alert(alert_info)
                logger.debug(f"Saved alert info for alert: '{summary}' to sent_alerts.json")
                
                # Start auto-resolve task
                asyncio.create_task(auto_resolve_alert(
                    duration, summary, description, severity, service, {}, {}, alert_id
                ))
                
                logger.info(f"Successfully generated alert #{i+1}/{count}: '{summary}'")
                generated_count += 1
            else:
                errors.append(f"Alert {i+1}: {message}")
                logger.error(f"Failed to generate alert #{i+1}: '{summary}' - {message}")
                
        except Exception as e:
            errors.append(f"Alert {i+1}: {str(e)}")
            logger.error(f"Exception generating alert #{i+1}: {str(e)}", exc_info=True)
    
    logger.info(f"Bulk generation completed - Successfully generated: {generated_count}/{count} alerts, Errors: {len(errors)}")
    if errors:
        logger.warning(f"Errors during bulk generation: {errors}")
    
    sent_alerts = get_sent_alerts()
    return templates.TemplateResponse("bulk_generate.html", {
        "request": request,
        "alertmanager_url": ALERTMANAGER_URL,
        "sent_alerts": sent_alerts,
        "message": f"Generated {generated_count} alerts successfully" + (f". Errors: {len(errors)}" if errors else ""),
        "message_type": "success" if generated_count > 0 else "error"
    })

@app.post("/resolve-alert/{alert_id}")
async def resolve_alert_endpoint(alert_id: str):
    """Resolve a specific alert"""
    success, message = resolve_sent_alert(alert_id)
    return {"success": success, "message": message}

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

@app.get("/alerts/status")
async def alerts_status():
    """Get status of all alerts"""
    alerts = load_sent_alerts()
    return {
        "total_alerts": len(alerts),
        "alerts": alerts,
        "alerts_directory": ALERTS_DIR
    }

if __name__ == "__main__":
    port = int(os.environ.get("ADAM_PORT", 5067))
    uvicorn.run(app, host="0.0.0.0", port=port)
