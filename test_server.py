#!/usr/bin/env python3
"""
Mock API server for testing Lovelace CLI
Run with: python test_server.py
"""

from flask import Flask, request, jsonify
import jwt
import datetime
import uuid

app = Flask(__name__)
SECRET_KEY = "test-secret-key"

# Mock data
MOCK_USER = {
    "username": "testuser",
    "password": "testpass",
    "user_id": "user-123"
}

MOCK_PROJECTS = [
    {"id": "proj-1", "name": "Test Project 1"},
    {"id": "proj-2", "name": "Test Project 2"},
]

MOCK_PROJECT_CONFIG = {
    "proj-1": {
        "name": "Test Project 1",
        "bucket": "test-bucket",
        "prefix": "projects/project1",
        "access_key_id": "AKIAIOSFODNN7EXAMPLE",
        "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "endpoint_url": "https://localhost:4566",  # LocalStack S3
        "websocket_url": "ws://localhost:8080/ws"
    }
}

@app.route('/api/cli/auth', methods=['POST'])
def auth():
    data = request.json
    
    if data.get('username') == MOCK_USER['username'] and \
       data.get('password') == MOCK_USER['password']:
        
        # Generate access token (5 min)
        access_token = jwt.encode({
            'user_id': MOCK_USER['user_id'],
            'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=5)
        }, SECRET_KEY, algorithm='HS256')
        
        return jsonify({
            'access_token': access_token,
            'projects': MOCK_PROJECTS
        })
    
    return jsonify({'error': 'Invalid credentials'}), 401

@app.route('/api/cli/auth/project', methods=['POST'])
def auth_project():
    data = request.json
    
    # Verify access token
    try:
        payload = jwt.decode(data.get('access_token'), SECRET_KEY, algorithms=['HS256'])
    except:
        return jsonify({'error': 'Invalid token'}), 401
    
    project_id = data.get('project_id')
    if project_id not in MOCK_PROJECT_CONFIG:
        return jsonify({'error': 'Project not found'}), 404
    
    # Generate project token (30 days)
    project_token = jwt.encode({
        'user_id': payload['user_id'],
        'project_id': project_id,
        'device_id': str(uuid.uuid4()),
        'exp': datetime.datetime.utcnow() + datetime.timedelta(days=30)
    }, SECRET_KEY, algorithm='HS256')
    
    config = MOCK_PROJECT_CONFIG[project_id].copy()
    config['token'] = project_token
    
    return jsonify(config)

@app.route('/api/cli/auth/validate', methods=['POST'])
def validate():
    data = request.json
    
    try:
        payload = jwt.decode(data.get('token'), SECRET_KEY, algorithms=['HS256'])
        project_id = payload.get('project_id')
        
        if project_id in MOCK_PROJECT_CONFIG:
            config = MOCK_PROJECT_CONFIG[project_id]
            return jsonify({
                'valid': True,
                'prefix': config['prefix'],
                'bucket': config['bucket'],
                'endpoint_url': config['endpoint_url'],
                'websocket_url': config['websocket_url']
            })
    except:
        pass
    
    return jsonify({'valid': False}), 401

if __name__ == '__main__':
    print("Mock API server running on http://localhost:5000")
    print("Test credentials: testuser / testpass")
    app.run(debug=True, port=5000)