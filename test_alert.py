#!/usr/bin/env python3
"""
Test script to demonstrate sending alerts using amtool command.
This script shows how the amtool command is constructed and executed.
"""

import subprocess
import json

def test_amtool_alert():
    """Test sending an alert using amtool command"""
    
    # Alert details
    summary = "Test Alert"
    description = "This is a test alert sent from ADAM"
    severity = "warning"
    duration = "5m"
    service = "test-service"
    custom_labels = {
        "environment": "development",
        "team": "devops"
    }
    
    # Alertmanager URL
    alertmanager_url = "http://localhost:9093"
    
    # Build amtool command
    cmd = [
        'amtool', 'alert', 'add', summary,
        f'severity={severity}',
        f'service={service}',
        f'--annotation=summary="{summary}"',
        f'--annotation=description="{description}"',
        f'--alertmanager.url={alertmanager_url}'
        f'--duration="{duration}"',
    ]
    
    # Add custom labels
    for label_key, label_value in custom_labels.items():
        if label_key and label_value:
            cmd.append(f'{label_key}={label_value}')
    
    print("Command that would be executed:")
    print(" ".join(cmd))
    print()
    
    try:
        # Execute amtool command
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            print("✅ Alert sent successfully!")
            print("Output:", result.stdout)
        else:
            print("❌ Failed to send alert")
            print("Error:", result.stderr)
            print("Return code:", result.returncode)
            
    except subprocess.TimeoutExpired:
        print("❌ Timeout while sending alert")
    except FileNotFoundError:
        print("❌ amtool command not found. Please install Alertmanager tools.")
    except Exception as e:
        print(f"❌ Error sending alert: {str(e)}")

if __name__ == "__main__":
    print("Testing amtool alert functionality...")
    print("Make sure Alertmanager is running on http://localhost:9093")
    print()
    test_amtool_alert() 