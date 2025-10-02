import json
import logging
import time
import threading
from typing import Dict, Optional, Callable
from datetime import datetime, timedelta
import websocket
from websocket import WebSocketApp
from .sync import R2Sync

logger = logging.getLogger(__name__)

class WatchError(Exception):
    pass

class WebSocketWatcher:
    def __init__(self, config: Dict[str, str], sync_handler: R2Sync):
        self.websocket_url = config.get("websocket_url")
        self.token = config.get("token")
        self.project_id = config.get("project_id")
        self.sync_handler = sync_handler
        self.ws_app: Optional[WebSocketApp] = None
        self.running = False
        self.reconnect_delay = 5
        self.max_reconnect_delay = 60
        self.last_activity = datetime.now()
        self.hibernation_timeout = 30
        self.ping_interval = 25
        
    def _on_open(self, ws):
        logger.info("WebSocket connection established")
        self.reconnect_delay = 5
        
        # Send authentication message to API gateway
        # The API gateway expects projectId in the auth message
        # Use the project_id from config, not from parsing the prefix
        auth_message = json.dumps({
            "type": "auth",
            "token": self.token,
            "projectId": self.project_id
        })
        ws.send(auth_message)
    
    
    def _on_message(self, ws, message):
        try:
            self.last_activity = datetime.now()
            data = json.loads(message)
            msg_type = data.get("type")
            
            if msg_type == "auth_success":
                logger.info("Authentication successful")
                
                restore_message = json.dumps({"type": "restore_state"})
                ws.send(restore_message)
                
            elif msg_type == "state_restored":
                logger.info(f"State restored: {data.get('state', {})}")
                
            elif msg_type == "file_change":
                file_path = data.get("path")
                change_type = data.get("change_type")
                
                logger.info(f"File change detected: {change_type} - {file_path}")
                
                if change_type in ["create", "update"]:
                    self._handle_file_update(file_path)
                elif change_type == "delete":
                    self._handle_file_delete(file_path)
                    
            elif msg_type == "pending_changes":
                changes = data.get("changes", [])
                logger.info(f"Received {len(changes)} pending changes")
                
                for change in changes:
                    file_path = change.get("path")
                    change_type = change.get("event")
                    
                    if change_type in ["created", "updated"]:
                        self._handle_file_update(file_path)
                    elif change_type == "deleted":
                        self._handle_file_delete(file_path)
                    
            elif msg_type == "pong":
                logger.debug("Received pong")
                
            elif msg_type == "error":
                logger.error(f"Server error: {data.get('message')}")
                
            elif msg_type == "auth_error":
                logger.error(f"Authentication error: {data.get('message')}")
                # Close connection on auth error
                ws.close()
                
            elif msg_type == "hibernating":
                logger.info(f"Server hibernating: {data.get('message')}")
                # Server is hibernating, we'll reconnect when needed
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse message: {e}")
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    
    def _handle_file_update(self, file_path: str):
        try:
            remote_key = f"{self.sync_handler.prefix}/{file_path}".lstrip('/')
            local_path = self.sync_handler.local_root / file_path
            
            success = self.sync_handler._download_file(remote_key, local_path)
            if success:
                logger.info(f"Successfully synced: {file_path}")
            else:
                logger.error(f"Failed to sync: {file_path}")
                
        except Exception as e:
            logger.error(f"Error syncing file {file_path}: {e}")
    
    def _handle_file_delete(self, file_path: str):
        try:
            local_path = self.sync_handler.local_root / file_path
            
            if local_path.exists():
                local_path.unlink()
                logger.info(f"Deleted local file: {file_path}")
                
                parent = local_path.parent
                while parent != self.sync_handler.local_root:
                    try:
                        if not any(parent.iterdir()):
                            parent.rmdir()
                            logger.info(f"Removed empty directory: {parent}")
                    except:
                        break
                    parent = parent.parent
                    
        except Exception as e:
            logger.error(f"Error deleting file {file_path}: {e}")
    
    def _on_error(self, ws, error):
        logger.error(f"WebSocket error: {error}")
    
    def _on_close(self, ws, close_status_code, close_msg):
        logger.info(f"WebSocket connection closed: {close_status_code} - {close_msg}")
        
        if self.running:
            inactive_time = datetime.now() - self.last_activity
            if inactive_time > timedelta(seconds=self.hibernation_timeout):
                self._save_state(ws)
            
            logger.info(f"Reconnecting in {self.reconnect_delay} seconds...")
            time.sleep(self.reconnect_delay)
            
            self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)
            
            if self.running:
                self._connect()
    
    def _save_state(self, ws):
        try:
            state = {
                "last_sync": self.last_activity.isoformat(),
                "prefix": self.sync_handler.prefix
            }
            
            save_message = json.dumps({
                "type": "save_state",
                "state": state
            })
            
            if ws.sock and ws.sock.connected:
                ws.send(save_message)
                logger.info("Saved state for hibernation")
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
    
    def _connect(self):
        try:
            # Construct the WebSocket URL for the API gateway
            # The API gateway expects the format: wss://domain/api/cli/sync/{projectId}
            websocket_url = f"{self.websocket_url}/api/cli/sync/{self.project_id}"
            
            logger.info(f"Connecting to WebSocket: {websocket_url}")
            
            # The websocket-client library handles WebSocket upgrade headers automatically
            # No need to manually set Upgrade, Connection, or Sec-WebSocket headers
            
            self.ws_app = WebSocketApp(
                websocket_url,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close
            )
            
            # Run the WebSocket connection with proper parameters for upgrade handling
            wst = threading.Thread(target=self._run_websocket)
            wst.daemon = True
            wst.start()
            
        except Exception as e:
            logger.error(f"Failed to establish WebSocket connection: {e}")
            raise WatchError(f"WebSocket connection failed: {e}")
    
    def _run_websocket(self):
        """Run the WebSocket connection with proper error handling"""
        try:
            # Use run_forever with ping_interval and ping_timeout for better connection handling
            # Also include origin and host headers for proper WebSocket upgrade
            self.ws_app.run_forever(
                ping_interval=self.ping_interval,
                ping_timeout=10,
                ping_payload='{"type": "ping"}',
                origin=None,  # Let the library handle origin
                host=None     # Let the library handle host
            )
        except Exception as e:
            logger.error(f"WebSocket connection error: {e}")
            if self.running:
                # Attempt to reconnect if we're still supposed to be running
                logger.info("Attempting to reconnect...")
                time.sleep(self.reconnect_delay)
                if self.running:
                    self._connect()
    
    def start(self):
        if self.running:
            logger.warning("Watcher is already running")
            return
        
        logger.info("Starting file watcher...")
        self.running = True
        
        logger.info("Performing initial sync...")
        try:
            downloaded, updated, deleted = self.sync_handler.sync()
            logger.info(f"Initial sync complete: {len(downloaded)} new, {len(updated)} updated, {len(deleted)} deleted")
        except Exception as e:
            logger.error(f"Initial sync failed: {e}")
        
        self._connect()
    
    def stop(self):
        logger.info("Stopping file watcher...")
        self.running = False
        
        if self.ws_app:
            self.ws_app.close()
            self.ws_app = None
        
        logger.info("File watcher stopped")