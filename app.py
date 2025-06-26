# app.py - Main Flask application
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import pandas as pd
import json
from datetime import datetime
import os
from urllib.parse import urlparse
import threading
import time

app = Flask(__name__)
CORS(app)  # Allow cross-origin requests from React frontend

# Configuration
TIMEOUT = 10  # Request timeout in seconds
MAX_WORKERS = 10  # Maximum concurrent requests

def format_url(domain):
    """Format domain to proper URL format"""
    if not domain.startswith(('http://', 'https://')):
        return f'https://{domain}'
    return domain

def check_website_status(url):
    """Check the status of a single website"""
    try:
        formatted_url = format_url(url)
        
        # Make HTTP request with timeout
        response = requests.get(
            formatted_url, 
            timeout=TIMEOUT,
            allow_redirects=True,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
        )
        
        status_code = response.status_code
        message = get_status_message(status_code)
        
        return {
            'domain': url,
            'status': status_code,
            'message': message,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'response_time': response.elapsed.total_seconds()
        }
        
    except requests.exceptions.Timeout:
        return {
            'domain': url,
            'status': 'TIMEOUT',
            'message': '⏱️ Request Timeout',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'response_time': None
        }
    except requests.exceptions.ConnectionError:
        return {
            'domain': url,
            'status': 'CONNECTION_ERROR',
            'message': '❌ Connection Failed',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'response_time': None
        }
    except Exception as e:
        return {
            'domain': url,
            'status': 'ERROR',
            'message': f'❌ Error: {str(e)[:50]}',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'response_time': None
        }

def get_status_message(status_code):
    """Get user-friendly message for HTTP status code"""
    messages = {
        200: '✅ Site is Live',
        201: '✅ Created',
        204: '✅ No Content',
        301: '↗️ Moved Permanently',
        302: '↗️ Found (Redirect)',
        304: '📋 Not Modified',
        400: '❌ Bad Request',
        401: '🔒 Unauthorized',
        403: '🔒 Access Forbidden',
        404: '❌ 404 Not Found',
        405: '❌ Method Not Allowed',
        408: '⏱️ Request Timeout',
        429: '⚠️ Too Many Requests',
        500: '⚠️ Internal Server Error',
        502: '⚠️ Bad Gateway',
        503: '⚠️ Service Unavailable',
        504: '⚠️ Gateway Timeout'
    }
    
    if status_code in messages:
        return messages[status_code]
    elif 200 <= status_code < 300:
        return '✅ Success'
    elif 300 <= status_code < 400:
        return '↗️ Redirect'
    elif 400 <= status_code < 500:
        return '❌ Client Error'
    elif 500 <= status_code < 600:
        return '⚠️ Server Error'
    else:
        return '❓ Unknown Status'

@app.route('/api/check-single', methods=['POST'])
def check_single_domain():
    """Check status of a single domain"""
    data = request.get_json()
    
    if not data or 'domain' not in data:
        return jsonify({'error': 'Domain is required'}), 400
    
    domain = data['domain'].strip()
    if not domain:
        return jsonify({'error': 'Domain cannot be empty'}), 400
    
    result = check_website_status(domain)
    return jsonify(result)

@app.route('/api/check-bulk', methods=['POST'])
def check_bulk_domains():
    """Check status of multiple domains"""
    data = request.get_json()
    
    if not data or 'domains' not in data:
        return jsonify({'error': 'Domains list is required'}), 400
    
    domains = data['domains']
    if not isinstance(domains, list):
        return jsonify({'error': 'Domains must be a list'}), 400
    
    if len(domains) == 0:
        return jsonify({'error': 'At least one domain is required'}), 400
    
    if len(domains) > 100:  # Limit to prevent abuse
        return jsonify({'error': 'Maximum 100 domains allowed'}), 400
    
    results = []
    
    # Process domains sequentially (you can implement threading for better performance)
    for domain in domains:
        if domain.strip():  # Skip empty domains
            result = check_website_status(domain.strip())
            results.append(result)
    
    # Calculate summary
    summary = {
        'total': len(results),
        'active': sum(1 for r in results if isinstance(r['status'], int) and 200 <= r['status'] < 300),
        'inactive': sum(1 for r in results if isinstance(r['status'], int) and 400 <= r['status'] < 500),
        'errors': sum(1 for r in results if not isinstance(r['status'], int) or r['status'] >= 500),
        'redirects': sum(1 for r in results if isinstance(r['status'], int) and 300 <= r['status'] < 400)
    }
    
    return jsonify({
        'results': results,
        'summary': summary
    })

@app.route('/api/upload-file', methods=['POST'])
def upload_file():
    """Process uploaded CSV/Excel file and extract domains"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    try:
        filename = file.filename.lower()
        domains = []
        
        if filename.endswith('.csv'):
            # Read CSV file
            df = pd.read_csv(file)
            
            # Try to find domain column (check common column names)
            domain_columns = ['domain', 'url', 'website', 'site', 'domains', 'urls']
            domain_column = None
            
            for col in df.columns:
                if col.lower().strip() in domain_columns:
                    domain_column = col
                    break
            
            if domain_column:
                domains = df[domain_column].dropna().astype(str).tolist()
            else:
                # If no specific column found, use first column
                domains = df.iloc[:, 0].dropna().astype(str).tolist()
                
        elif filename.endswith(('.xlsx', '.xls')):
            # Read Excel file
            df = pd.read_excel(file)
            
            # Try to find domain column
            domain_columns = ['domain', 'url', 'website', 'site', 'domains', 'urls']
            domain_column = None
            
            for col in df.columns:
                if col.lower().strip() in domain_columns:
                    domain_column = col
                    break
            
            if domain_column:
                domains = df[domain_column].dropna().astype(str).tolist()
            else:
                # If no specific column found, use first column
                domains = df.iloc[:, 0].dropna().astype(str).tolist()
        else:
            return jsonify({'error': 'Unsupported file format. Please use CSV or Excel files.'}), 400
        
        # Clean and filter domains
        cleaned_domains = []
        for domain in domains:
            domain = domain.strip()
            if domain and '.' in domain and not domain.startswith('#'):
                cleaned_domains.append(domain)
        
        if not cleaned_domains:
            return jsonify({'error': 'No valid domains found in the file'}), 400
        
        return jsonify({
            'domains': cleaned_domains[:100],  # Limit to 100 domains
            'total_found': len(cleaned_domains)
        })
        
    except Exception as e:
        return jsonify({'error': f'Error processing file: {str(e)}'}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'version': '1.0.0'
    })

@app.route('/', methods=['GET'])
def home():
    """Home endpoint with API documentation"""
    return jsonify({
        'message': 'Website Status Checker API',
        'version': '1.0.0',
        'endpoints': {
            'POST /api/check-single': 'Check single domain status',
            'POST /api/check-bulk': 'Check multiple domains status',
            'POST /api/upload-file': 'Upload and process CSV/Excel file',
            'GET /api/health': 'Health check'
        },
        'documentation': {
            'check-single': {
                'method': 'POST',
                'body': {'domain': 'example.com'},
                'description': 'Check status of a single domain'
            },
            'check-bulk': {
                'method': 'POST',
                'body': {'domains': ['example.com', 'google.com']},
                'description': 'Check status of multiple domains'
            }
        }
    })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)