#!/usr/bin/env python3
"""
Script for generating files based on example.yml
Modifies alertname, summary and ts in each generated file
"""

import yaml
import argparse
import os
import time
from typing import List, Dict, Any
from pathlib import Path


def load_template(template_path: str = 'example.yml') -> Dict[str, Any]:
    """Loads template from example.yml"""
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template {template_path} not found")
    
    with open(template_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def update_alert_data(data: Dict[str, Any], alertname: str, summary: str, ts: str) -> Dict[str, Any]:
    """Updates alertname, summary and ts in the data structure"""
    # Create a copy of the data
    updated_data = yaml.safe_load(yaml.dump(data))
    
    # Update alertname in multiple places
    if 'payload' in updated_data:
        # In alerts[0].labels.alertname
        if 'alerts' in updated_data['payload'] and len(updated_data['payload']['alerts']) > 0:
            if 'labels' in updated_data['payload']['alerts'][0]:
                updated_data['payload']['alerts'][0]['labels']['alertname'] = alertname
        
        # In commonLabels.alertname
        if 'commonLabels' in updated_data['payload']:
            updated_data['payload']['commonLabels']['alertname'] = alertname
        
        # In groupLabels.alertname
        if 'groupLabels' in updated_data['payload']:
            updated_data['payload']['groupLabels']['alertname'] = alertname
        
        # Update groupKey with new alertname
        if 'groupKey' in updated_data['payload']:
            updated_data['payload']['groupKey'] = f'{{}}:{{alertname="{alertname}"}}'
        
        # Update summary in two places
        if 'alerts' in updated_data['payload'] and len(updated_data['payload']['alerts']) > 0:
            if 'annotations' in updated_data['payload']['alerts'][0]:
                updated_data['payload']['alerts'][0]['annotations']['summary'] = summary
        
        if 'commonAnnotations' in updated_data['payload']:
            updated_data['payload']['commonAnnotations']['summary'] = summary
    
    # Update ts
    updated_data['ts'] = ts
    
    return updated_data


def save_yaml_file(data: Dict[str, Any], output_path: str):
    """Saves data to a YAML file"""
    with open(output_path, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def generate_ts() -> str:
    """Generates current timestamp in the format used in example.yml (e.g., '1763703334.262219')"""
    timestamp = time.time()
    return f"{timestamp:.6f}"


def generate_files(
    template_path: str,
    output_dir: str,
    alertnames: List[str],
    filename_pattern: str = "{alertname}.yml"
):
    """Generates files based on a list of alertnames"""
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Load template
    template = load_template(template_path)
    
    generated_files = []
    
    for idx, alertname in enumerate(alertnames, start=1):
        # Automatically generate summary
        summary = f"summary_{idx}"
        # Automatically generate ts
        ts = generate_ts()
        
        # Update data
        updated_data = update_alert_data(template, alertname, summary, ts)
        
        # Form filename
        filename = filename_pattern.format(alertname=alertname, summary=summary, ts=ts, num=idx)
        output_path = os.path.join(output_dir, filename)
        
        # Save file
        save_yaml_file(updated_data, output_path)
        generated_files.append(output_path)
        print(f"✓ Created file: {output_path}")
    
    return generated_files


def main():
    parser = argparse.ArgumentParser(
        description='File generator based on example.yml',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Usage examples:

1. Generate N files with automatic names:
   python bulk_generator.py --count 5

2. Generate files from CSV (alertname only):
   python bulk_generator.py --csv alerts.csv

3. Generate files from JSON (array of alertnames):
   python bulk_generator.py --json alerts.json

4. Generate with specified output directory:
   python bulk_generator.py --count 3 --output-dir generated

Note: summary is automatically generated as "summary_1", "summary_2", etc.
        """
    )
    
    parser.add_argument(
        '--template',
        default='example.yml',
        help='Path to template (default: example.yml)'
    )
    
    parser.add_argument(
        '--output-dir',
        default='generated',
        help='Directory for saving generated files (default: generated)'
    )
    
    parser.add_argument(
        '--count',
        type=int,
        help='Number of files to generate (alertname will be Alert1, Alert2, ...)'
    )
    
    parser.add_argument(
        '--csv',
        help='Path to CSV file with alertnames (format: alertname or alertname,alertname2,...)'
    )
    
    parser.add_argument(
        '--json',
        help='Path to JSON file with array of alertnames or objects with alertname field'
    )
    
    parser.add_argument(
        '--filename-pattern',
        default='{alertname}.yml',
        help='Filename pattern (default: {alertname}.yml)'
    )
    
    args = parser.parse_args()
    
    alertnames = []
    
    # Determine data source
    if args.csv:
        import csv
        with open(args.csv, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # If alertname column exists, use it
                if 'alertname' in row:
                    alertname = row['alertname'].strip()
                    if alertname:
                        alertnames.append(alertname)
                # Otherwise try to read the first column
                elif row:
                    alertname = list(row.values())[0].strip()
                    if alertname:
                        alertnames.append(alertname)
    elif args.json:
        import json
        with open(args.json, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                # If it's a list of strings
                if all(isinstance(item, str) for item in data):
                    alertnames = data
                # If it's a list of objects
                else:
                    for item in data:
                        if isinstance(item, dict) and 'alertname' in item:
                            alertnames.append(item['alertname'])
                        elif isinstance(item, str):
                            alertnames.append(item)
            elif isinstance(data, dict) and 'alertname' in data:
                alertnames = [data['alertname']]
    elif args.count:
        # Generate alertnames automatically
        alertnames = [f"Alert{i}" for i in range(1, args.count + 1)]
    else:
        parser.error("Must specify either --count, --csv, or --json")
    
    if not alertnames:
        parser.error("No alertnames found for generation")
    
    # Generate files
    print(f"Generating {len(alertnames)} file(s)...")
    generated_files = generate_files(
        args.template,
        args.output_dir,
        alertnames,
        args.filename_pattern
    )
    
    print(f"\n✓ Successfully generated {len(generated_files)} file(s) in directory {args.output_dir}")


if __name__ == '__main__':
    main()

