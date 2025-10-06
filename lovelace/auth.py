import click
import requests
import json
import platform
import socket
import hashlib
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

class AuthenticationError(Exception):
    pass

class AuthClient:
    def __init__(self, api_url: str = "https://api.lovelace.sh/api/cli/auth"):
        self.api_url = api_url
    
    def _get_device_id(self) -> str:
        """Generate a consistent device identifier"""
        import uuid
        import os
        
        # Try to get machine ID from various sources for consistency
        machine_id = None
        
        # Try macOS method
        if platform.system() == "Darwin":
            try:
                result = os.popen("ioreg -rd1 -c IOPlatformExpertDevice | grep IOPlatformUUID").read()
                if "IOPlatformUUID" in result:
                    machine_id = result.split('"')[-2]
            except:
                pass
        
        # Try Linux method
        elif platform.system() == "Linux":
            try:
                with open("/etc/machine-id", "r") as f:
                    machine_id = f.read().strip()
            except:
                try:
                    with open("/var/lib/dbus/machine-id", "r") as f:
                        machine_id = f.read().strip()
                except:
                    pass
        
        # Try Windows method
        elif platform.system() == "Windows":
            try:
                import subprocess
                result = subprocess.check_output("wmic csproduct get UUID", shell=True).decode()
                lines = result.strip().split('\n')
                if len(lines) > 1:
                    machine_id = lines[1].strip()
            except:
                pass
        
        # Fallback to MAC address if no machine ID found
        if not machine_id:
            machine_id = ':'.join(['{:02x}'.format((uuid.getnode() >> ele) & 0xff) 
                                   for ele in range(0,8*6,8)][::-1])
        
        hostname = socket.gethostname()
        
        # Create consistent hash from machine_id
        device_string = f"{machine_id}-{hostname}"
        device_hash = hashlib.sha256(device_string.encode()).hexdigest()[:8]
        
        return f"{hostname}-{device_hash}"
    
    def authenticate(self, username: str, password: str) -> Dict[str, Any]:
        """First step: authenticate and get projects list with short-lived access token"""
        try:
            response = requests.post(
                self.api_url,
                json={"username": username, "password": password},
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            if response.status_code == 200:
                response_json = response.json()
                
                # Check if success flag exists and is true
                if not response_json.get("success"):
                    raise AuthenticationError("Authentication failed")
                
                # Extract the data object
                data = response_json.get("data", {})
                
                if not data.get("access_token"):
                    raise AuthenticationError("No access token in response")
                
                return {
                    "access_token": data.get("access_token"),  # Short-lived token (5 min)
                    "projects": data.get("projects", []),  # List with id, name, type, description
                    "token_type": data.get("token_type", "Bearer"),
                    "expires_in": data.get("expires_in", 300),
                    "username": username  # Use the username that was provided since it's not in response
                }
            elif response.status_code == 401:
                raise AuthenticationError("Invalid credentials")
            else:
                raise AuthenticationError(f"Authentication failed: {response.status_code}")
                
        except requests.RequestException as e:
            logger.error(f"Network error during authentication: {e}")
            raise AuthenticationError(f"Network error: {str(e)}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid response format: {e}")
            raise AuthenticationError("Invalid response from server")
    
    def get_project_token(self, access_token: str, project_id: str, device_name: Optional[str] = None) -> Dict[str, Any]:
        """Second step: get project-specific configuration and long-lived token"""
        if not device_name:
            device_name = self._get_device_id()
        
        try:
            response = requests.post(
                f"{self.api_url}/project",
                json={
                    "access_token": access_token,
                    "project_id": project_id,
                    "device_name": device_name
                },
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            if response.status_code == 200:
                response_json = response.json()
                
                # Check if success flag exists and is true
                if not response_json.get("success"):
                    raise AuthenticationError("Failed to get project token")
                
                data = response_json.get("data", {})
                r2_creds = data.get("r2_credentials", {})
                project_cfg = data.get("project_config", {})
                
                return {
                    "token": data.get("project_token"),  # Long-lived project-specific token
                    "device_id": data.get("device_id"),
                    "device_name": device_name,
                    "project_id": project_cfg.get("project_id"),
                    "project_name": project_cfg.get("project_name"),
                    "access_key_id": r2_creds.get("access_key_id"),
                    "secret_access_key": r2_creds.get("secret_access_key"),
                    "session_token": r2_creds.get("session_token"),
                    "bucket": project_cfg.get("bucket"),
                    "prefix": project_cfg.get("prefix"),
                    "endpoint_url": project_cfg.get("endpoint_url"),
                    "region": project_cfg.get("region", "auto"),
                    "websocket_url": project_cfg.get("websocket_url")
                }
            elif response.status_code == 401:
                raise AuthenticationError("Access token invalid or expired")
            elif response.status_code == 404:
                raise AuthenticationError("Project not found")
            else:
                raise AuthenticationError(f"Failed to get project token: {response.status_code}")
                
        except requests.RequestException as e:
            logger.error(f"Network error getting project token: {e}")
            raise AuthenticationError(f"Network error: {str(e)}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid response format: {e}")
            raise AuthenticationError("Invalid response from server")
    
    def validate_token(self, token: str) -> Dict[str, Any]:
        try:
            response = requests.post(
                "https://api.lovelace.sh/api/cli/auth/validate",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                },
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("success") and data.get("data", {}).get("valid"):
                    return {
                        "valid": True,
                        "user_id": data.get("data", {}).get("user_id"),
                        "project_id": data.get("data", {}).get("project_id"),
                        "device_id": data.get("data", {}).get("device_id"),
                        "project_dir": data.get("data", {}).get("project_dir")
                    }
            return {"valid": False}
        except requests.RequestException:
            return {"valid": False}