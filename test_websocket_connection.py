#!/usr/bin/env python3
"""
Test script for WebSocket connection to the API gateway
This script tests the WebSocket connection to the lovelace-api-gateway project
"""

import json
import time
import websocket
from websocket import WebSocketApp

def test_websocket_connection():
    """Test WebSocket connection to the API gateway"""
    
    # Configuration - update these values as needed
    WEBSOCKET_URL = "ws://localhost:8787"  # Update to your API gateway URL
    PROJECT_ID = "test-project"  # Update to your project ID
    AUTH_TOKEN = "your-auth-token-here"  # Update to your auth token
    
    websocket_url = f"{WEBSOCKET_URL}/api/cli/sync/{PROJECT_ID}"
    
    print(f"Testing WebSocket connection to: {websocket_url}")
    
    def on_open(ws):
        print("✅ WebSocket connection opened")
        
        # Send authentication message
        auth_message = {
            "type": "auth",
            "token": AUTH_TOKEN,
            "projectId": PROJECT_ID
        }
        
        print(f"Sending auth message: {auth_message}")
        ws.send(json.dumps(auth_message))
    
    def on_message(ws, message):
        print(f"📩 Received message: {message}")
        
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            
            if msg_type == "auth_success":
                print("✅ Authentication successful")
            elif msg_type == "auth_error":
                print(f"❌ Authentication failed: {data.get('message')}")
            elif msg_type == "file_change":
                print(f"📁 File change: {data.get('path')} - {data.get('change_type')}")
            elif msg_type == "pending_changes":
                changes = data.get("changes", [])
                print(f"📋 Received {len(changes)} pending changes")
            elif msg_type == "pong":
                print("🏓 Received pong")
            elif msg_type == "error":
                print(f"❌ Server error: {data.get('message')}")
            elif msg_type == "hibernating":
                print(f"😴 Server hibernating: {data.get('message')}")
            else:
                print(f"❓ Unknown message type: {msg_type}")
                
        except json.JSONDecodeError as e:
            print(f"❌ Failed to parse message: {e}")
    
    def on_error(ws, error):
        print(f"❌ WebSocket error: {error}")
    
    def on_close(ws, close_status_code, close_msg):
        print(f"🔚 WebSocket closed. Code: {close_status_code}, Reason: {close_msg}")
    
    # Set up headers for authentication
    headers = {
        'Authorization': f'Bearer {AUTH_TOKEN}',
        'Upgrade': 'websocket',
        'Connection': 'Upgrade'
    }
    
    # Create WebSocket connection
    ws = WebSocketApp(
        websocket_url,
        header=headers,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    
    print("Starting WebSocket connection...")
    ws.run_forever()

if __name__ == "__main__":
    print("WebSocket Connection Test")
    print("=" * 50)
    print("Make sure to update the configuration variables:")
    print("- WEBSOCKET_URL: Your API gateway WebSocket URL")
    print("- PROJECT_ID: Your project ID")
    print("- AUTH_TOKEN: Your authentication token")
    print("=" * 50)
    
    test_websocket_connection()
