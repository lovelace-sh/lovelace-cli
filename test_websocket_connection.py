#!/usr/bin/env python3
"""
WebSocket Ping Test for Lovelace CLI
Tests WebSocket connection stability using ping/pong messages
"""

import json
import time
import threading
import ssl
import certifi
import websocket
from websocket import WebSocketApp
from datetime import datetime
import sys
import os

class WebSocketPingTester:
    def __init__(self, websocket_url="wss://dev.api.lovelace.sh", project_id="test-project", auth_token="test-token"):
        self.websocket_url = f"{websocket_url}/api/cli/sync/{project_id}"
        self.project_id = project_id
        self.auth_token = auth_token
        self.ws = None
        self.connected = False
        self.ping_count = 0
        self.pong_count = 0
        self.ping_interval = 5  # seconds
        self.ping_timeout = 10  # seconds
        self.last_ping_time = None
        self.ping_timer = None
        self.test_duration = 60  # seconds
        self.start_time = None
        self.results = {
            'pings_sent': 0,
            'pongs_received': 0,
            'connection_attempts': 0,
            'connection_failures': 0,
            'avg_response_time': 0,
            'response_times': []
        }

    def log(self, message, level="INFO"):
        """Log message with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{timestamp}] [{level}] {message}")

    def send_ping(self):
        """Send ping message to server"""
        if not self.connected or not self.ws:
            return False
        
        try:
            ping_message = {
                "type": "ping",
                "timestamp": time.time(),
                "ping_id": self.ping_count
            }
            
            self.ws.send(json.dumps(ping_message))
            self.ping_count += 1
            self.results['pings_sent'] += 1
            self.last_ping_time = time.time()
            self.log(f"🏓 Sent ping #{self.ping_count}")
            return True
        except Exception as e:
            self.log(f"❌ Failed to send ping: {e}", "ERROR")
            return False

    def schedule_next_ping(self):
        """Schedule the next ping"""
        if self.ping_timer:
            self.ping_timer.cancel()
        
        if self.connected:
            self.ping_timer = threading.Timer(self.ping_interval, self.send_ping)
            self.ping_timer.start()

    def on_open(self, ws):
        """Handle WebSocket connection open"""
        self.connected = True
        self.results['connection_attempts'] += 1
        self.log("✅ WebSocket connection opened")
        
        # Send authentication message
        auth_message = {
            "type": "auth",
            "token": self.auth_token,
            "projectId": self.project_id
        }
        
        self.log(f"Sending auth message: {auth_message}")
        ws.send(json.dumps(auth_message))
        
        # Start ping sequence after a short delay
        threading.Timer(2, self.send_ping).start()

    def on_message(self, ws, message):
        """Handle incoming WebSocket messages"""
        self.log(f"📩 Received: {message}")
        
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            
            if msg_type == "auth_success":
                self.log("✅ Authentication successful")
                self.schedule_next_ping()
                
            elif msg_type == "auth_error":
                self.log(f"❌ Authentication failed: {data.get('message')}", "ERROR")
                self.results['connection_failures'] += 1
                
            elif msg_type == "pong":
                self.pong_count += 1
                self.results['pongs_received'] += 1
                
                # Calculate response time
                if self.last_ping_time:
                    response_time = time.time() - self.last_ping_time
                    self.results['response_times'].append(response_time)
                    self.log(f"🏓 Received pong #{self.pong_count} (response time: {response_time:.3f}s)")
                else:
                    self.log(f"🏓 Received pong #{self.pong_count}")
                
                # Schedule next ping
                self.schedule_next_ping()
                
            elif msg_type == "error":
                self.log(f"❌ Server error: {data.get('message')}", "ERROR")
                
            elif msg_type == "hibernating":
                self.log(f"😴 Server hibernating: {data.get('message')}")
                
            else:
                self.log(f"❓ Unknown message type: {msg_type}")
                
        except json.JSONDecodeError as e:
            self.log(f"❌ Failed to parse message: {e}", "ERROR")

    def on_error(self, ws, error):
        """Handle WebSocket errors"""
        self.log(f"❌ WebSocket error: {error}", "ERROR")
        self.results['connection_failures'] += 1
        self.connected = False

    def on_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket connection close"""
        self.connected = False
        if self.ping_timer:
            self.ping_timer.cancel()
        self.log(f"🔚 WebSocket closed. Code: {close_status_code}, Reason: {close_msg}")

    def calculate_stats(self):
        """Calculate test statistics"""
        if self.results['response_times']:
            self.results['avg_response_time'] = sum(self.results['response_times']) / len(self.results['response_times'])
            self.results['min_response_time'] = min(self.results['response_times'])
            self.results['max_response_time'] = max(self.results['response_times'])
        
        self.results['success_rate'] = (self.results['pongs_received'] / self.results['pings_sent']) * 100 if self.results['pings_sent'] > 0 else 0
        self.results['test_duration'] = time.time() - self.start_time if self.start_time else 0

    def print_results(self):
        """Print test results"""
        self.calculate_stats()
        
        print("\n" + "="*60)
        print("🏓 WEBSOCKET PING TEST RESULTS")
        print("="*60)
        print(f"Test Duration: {self.results['test_duration']:.1f} seconds")
        print(f"Connection Attempts: {self.results['connection_attempts']}")
        print(f"Connection Failures: {self.results['connection_failures']}")
        print(f"Pings Sent: {self.results['pings_sent']}")
        print(f"Pongs Received: {self.results['pongs_received']}")
        print(f"Success Rate: {self.results['success_rate']:.1f}%")
        
        if self.results['response_times']:
            print(f"Average Response Time: {self.results['avg_response_time']:.3f}s")
            print(f"Min Response Time: {self.results['min_response_time']:.3f}s")
            print(f"Max Response Time: {self.results['max_response_time']:.3f}s")
        
        print("="*60)
        
        # Test result summary
        if self.results['success_rate'] >= 90:
            print("✅ TEST PASSED: Excellent connection stability")
        elif self.results['success_rate'] >= 70:
            print("⚠️  TEST WARNING: Good connection with some issues")
        else:
            print("❌ TEST FAILED: Poor connection stability")

    def run_test(self, duration=60):
        """Run the ping test for specified duration"""
        self.test_duration = duration
        self.start_time = time.time()
        
        print(f"🚀 Starting WebSocket Ping Test")
        print(f"Target: {self.websocket_url}")
        print(f"Duration: {duration} seconds")
        print(f"Ping Interval: {self.ping_interval} seconds")
        print("-" * 60)
        
        # Set up headers for authentication
        headers = {
            'Authorization': f'Bearer {self.auth_token}',
            'Upgrade': 'websocket',
            'Connection': 'Upgrade'
        }
        
        # Create WebSocket connection
        self.ws = WebSocketApp(
            self.websocket_url,
            header=headers,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
        
        try:
            # Configure SSL context with proper certificate verification
            ssl_context = ssl.create_default_context()
            ssl_context.load_verify_locations(certifi.where())
            
            # Run the test for specified duration with SSL configuration
            self.ws.run_forever(sslopt={"context": ssl_context})
        except KeyboardInterrupt:
            self.log("Test interrupted by user")
        except Exception as e:
            self.log(f"Test error: {e}", "ERROR")
        finally:
            if self.ping_timer:
                self.ping_timer.cancel()
            self.print_results()

def main():
    """Main test function"""
    print("WebSocket Ping Test for Lovelace CLI")
    print("=" * 50)
    
    # Configuration - update these as needed
    WEBSOCKET_URL = "wss://dev.api.lovelace.sh"
    PROJECT_ID = ""
    AUTH_TOKEN = ""
    TEST_DURATION = 60  # seconds
    
    # Parse command line arguments
    if len(sys.argv) > 1:
        try:
            TEST_DURATION = int(sys.argv[1])
        except ValueError:
            print("Invalid duration. Using default 60 seconds.")
    
    # Override with environment variables if available
    WEBSOCKET_URL = os.getenv('WEBSOCKET_URL', WEBSOCKET_URL)
    PROJECT_ID = os.getenv('PROJECT_ID', PROJECT_ID)
    AUTH_TOKEN = os.getenv('AUTH_TOKEN', AUTH_TOKEN)
    
    print(f"Configuration:")
    print(f"  WebSocket URL: {WEBSOCKET_URL}")
    print(f"  Project ID: {PROJECT_ID}")
    print(f"  Auth Token: {AUTH_TOKEN[:10]}..." if len(AUTH_TOKEN) > 10 else f"  Auth Token: {AUTH_TOKEN}")
    print(f"  Test Duration: {TEST_DURATION} seconds")
    print()
    
    # Create and run the test
    tester = WebSocketPingTester(WEBSOCKET_URL, PROJECT_ID, AUTH_TOKEN)
    tester.run_test(TEST_DURATION)

if __name__ == "__main__":
    main()
