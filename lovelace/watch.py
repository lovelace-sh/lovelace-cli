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
        self.sync_handler = sync_handler
        self.ws_app: Optional[WebSocketApp] = None
        self.running = False
        self.reconnect_delay = 5
        self.max_reconnect_delay = 60
        self.last_activity = datetime.now()
        self.hibernation_timeout = 30
        self.ping_interval = 25
        self.ping_thread: Optional[threading.Thread] = None
        
    def _on_open(self, ws):
        logger.info("WebSocket connection established")
        self.reconnect_delay = 5
        
        auth_message = json.dumps({
            "type": "auth",
            "token": self.token
        })
        ws.send(auth_message)
        
        if self.ping_thread and self.ping_thread.is_alive():
            self.ping_thread.join()
        
        self.ping_thread = threading.Thread(target=self._ping_loop, args=(ws,))
        self.ping_thread.daemon = True
        self.ping_thread.start()
    
    def _ping_loop(self, ws):
        while self.running:
            time.sleep(self.ping_interval)
            if self.running and ws.sock and ws.sock.connected:
                try:
                    ws.send(json.dumps({"type": "ping"}))
                    logger.debug("Sent ping")
                except Exception as e:
                    logger.error(f"Failed to send ping: {e}")
                    break
    
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
                    
            elif msg_type == "pong":
                logger.debug("Received pong")
                
            elif msg_type == "error":
                logger.error(f"Server error: {data.get('message')}")
                
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
            self.ws_app = WebSocketApp(
                self.websocket_url,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close
            )
            
            wst = threading.Thread(target=self.ws_app.run_forever)
            wst.daemon = True
            wst.start()
            
        except Exception as e:
            logger.error(f"Failed to establish WebSocket connection: {e}")
            raise WatchError(f"WebSocket connection failed: {e}")
    
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
        
        if self.ping_thread and self.ping_thread.is_alive():
            self.ping_thread.join(timeout=5)
        
        logger.info("File watcher stopped")