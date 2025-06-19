# ADAM - Alert Manager

A simple web interface for sending alerts to Alertmanager using the standard `amtool` command, built with FastAPI.

## Features

- Simple web UI for creating alerts
- Form field history with autocomplete suggestions
- Support for custom labels
- Integration with Alertmanager via amtool
- Modern, responsive design
- FastAPI with async support
- Automatic API documentation

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

- `ADAM_PORT`: Port to run the web server on (default: 5067)
- `ALERTMANAGER_URL`: Alertmanager URL (default: http://localhost:9093)

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

## Development

The application uses:
- **FastAPI**: Modern, fast web framework
- **Uvicorn**: ASGI server for running FastAPI
- **Jinja2**: Template engine for HTML rendering
- **python-multipart**: For handling form data