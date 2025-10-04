# ADAM - Alert Manager

A simple web interface for sending alerts to Alertmanager using the standard `amtool` command, built with FastAPI.

## Features

- Simple web UI for creating alerts
- Form field history with autocomplete suggestions
- Support for custom labels and annotations
- Integration with Alertmanager via HTTP API
- Modern, responsive design
- FastAPI with async support
- Automatic API documentation
- **Alert storage in JSON files** - Each alert is stored as a separate JSON file in the `./alerts` directory
- **Alert management** - Close individual alerts or all alerts at once
- **Automatic cleanup** - Remove old alert files automatically
- **Debug logging** - Comprehensive logging with configurable levels

## Requirements

- Python 3.7+
- FastAPI
- Uvicorn
- amtool (Alertmanager command-line tool)

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Install amtool (Alertmanager tools):
```bash
# On Ubuntu/Debian
sudo apt-get install prometheus-alertmanager

# On CentOS/RHEL
sudo yum install prometheus2-alertmanager

# Or download from https://github.com/prometheus/alertmanager/releases
```

## Configuration

The application can be configured using environment variables:

- `ALERTMANAGER_URL`: Alertmanager URL (default: http://localhost:9093)
- `LOG_LEVEL`: Logging level - DEBUG, INFO, WARNING, ERROR, CRITICAL (default: DEBUG)
- `ADAM_PORT`: Port to run the web server on (default: 5067)

You can use environment variables in two ways:

1. **Direct environment variables**:
   ```bash
   export ALERTMANAGER_URL=http://localhost:9093
   export LOG_LEVEL=INFO
   export ADAM_PORT=5067
   python app.py
   ```

2. **Using .env file**:
   Create a `.env` file in the project root with:
   ```bash
   ALERTMANAGER_URL=http://localhost:9093
   LOG_LEVEL=INFO
   ADAM_PORT=5067
   ```
   
   Then run the application:
   ```bash
   python app.py
   ```

## Usage

1. Start the application:
```bash
python app.py
```

2. Open your browser and navigate to `http://localhost:5067`

3. Fill in the alert details:
   - **Summary**: Brief description of the alert
   - **Description**: Detailed description of the alert
   - **Severity**: Choose from info, warning, or critical
   - **Service**: Name of the service affected
   - **Custom Labels**: Optional key-value pairs for additional context

4. Click "Send Alert" to send the alert to Alertmanager

## API Documentation

FastAPI automatically generates interactive API documentation. After starting the server, visit:
- `http://localhost:5067/docs` - Swagger UI documentation
- `http://localhost:5067/redoc` - ReDoc documentation

## Form History

The application remembers previously entered values for:
- Summary
- Description  
- Service

These values appear as suggestions when you focus on the input fields, making it easier to reuse common values.

## Custom Labels

You can add custom labels to provide additional context for your alerts. Each label consists of a key-value pair that will be attached to the alert in Alertmanager.

## Alert Management

ADAM stores each alert as a separate JSON file in the `./alerts` directory. This allows for better organization and management of alerts.

### API Endpoints for Alert Management

- `POST /resolve-alert/{alert_id}` - Resolve a specific alert by ID
- `POST /close-all-alerts` - Close all active alerts at once
- `POST /cleanup-old-alerts?days_old=7` - Remove alert files older than specified days
- `GET /alerts/status` - Get status of all alerts

### Alert File Structure

Each alert is stored as `{alert_id}.json` with the following structure:
```json
{
  "id": "uuid-string",
  "summary": "Alert summary",
  "description": "Alert description",
  "severity": "warning",
  "service": "service-name",
  "duration": "5m",
  "custom_labels": {"key": "value"},
  "custom_annotations": {"key": "value"},
  "sent_at": "2024-01-01T12:00:00Z",
  "status": "active",
  "auto_resolve_scheduled": true
}
```

### Duration and Auto-Resolve

- **Duration field**: Each alert includes a `duration` field (e.g., "10s", "5m", "1h")
- **Automatic resolution**: Alerts are automatically resolved after the specified duration
- **Status tracking**: Alert status changes from "active" to "resolved" when auto-resolved
- **File cleanup**: Alert files are automatically removed after successful resolution

### Closing Alerts

Alerts can be closed in several ways:

1. **Automatic closure** - Alerts are automatically resolved after their specified duration
2. **Manual closure** - Use the API endpoints to close specific alerts
3. **Bulk closure** - Close all active alerts at once
4. **Cleanup** - Remove old alert files to free up space

## Development

The application uses:
- **FastAPI**: Modern, fast web framework
- **Uvicorn**: ASGI server for running FastAPI
- **Jinja2**: Template engine for HTML rendering
- **python-multipart**: For handling form data
- **python-dotenv**: For loading environment variables from .env files