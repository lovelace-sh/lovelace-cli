import json
import logging
import time
import threading
import ssl
import certifi
import click
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
        self.reconnect_delay = 5
        click.echo("Connected")

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
                # Skip restore_state for now to avoid server error
                # restore_message = json.dumps({"type": "restore_state"})
                # ws.send(restore_message)
                pass

            elif msg_type == "state_restored":
                pass
                
            elif msg_type == "file_change":
                file_path = data.get("path")
                change_type = data.get("event")

                if change_type in ["created", "updated"]:
                    self._handle_file_update(file_path, change_type)
                elif change_type == "deleted":
                    self._handle_file_delete(file_path)

            elif msg_type == "pending_changes":
                changes = data.get("changes", [])

                for change in changes:
                    file_path = change.get("path")
                    change_type = change.get("event")

                    if change_type in ["created", "updated"]:
                        self._handle_file_update(file_path, change_type)
                    elif change_type == "deleted":
                        self._handle_file_delete(file_path)
                    
            elif msg_type == "pong":
                pass

            elif msg_type == "error":
                logger.error(f"Server error: {data.get('message')}")

            elif msg_type == "auth_error":
                logger.error(f"Authentication error: {data.get('message')}")
                # Close connection on auth error
                ws.close()

            elif msg_type == "hibernating":
                # Server is hibernating, we'll reconnect when needed
                pass
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse message: {e}")
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    
    def _handle_file_update(self, file_path: str, change_type: str):
        try:
            # Construct the remote key the same way the sync command does
            # The remote key should be the full S3 key including the prefix
            if self.sync_handler.prefix:
                # Remove trailing slash from prefix and leading slash from file_path
                prefix = self.sync_handler.prefix.rstrip('/')
                file_path_clean = file_path.lstrip('/')
                remote_key = f"{prefix}/{file_path_clean}"
            else:
                remote_key = file_path.lstrip('/')

            local_path = self.sync_handler.local_root / file_path

            # Disable progress output for individual file downloads
            old_show_progress = self.sync_handler.show_progress
            self.sync_handler.show_progress = False
            success = self.sync_handler._download_file(remote_key, local_path)
            self.sync_handler.show_progress = old_show_progress

            if success and not file_path.endswith('.gitkeep'):
                action = "Created" if change_type == "created" else "Updated"
                click.echo(f"  ✓ {action} {file_path}")

        except Exception as e:
            logger.error(f"Error syncing file {file_path}: {e}")
    
    def _handle_file_delete(self, file_path: str):
        try:
            local_path = self.sync_handler.local_root / file_path

            if local_path.exists():
                local_path.unlink()
                if not file_path.endswith('.gitkeep'):
                    click.echo(f"  ✓ Deleted {file_path}")

                parent = local_path.parent
                while parent != self.sync_handler.local_root:
                    try:
                        if not any(parent.iterdir()):
                            parent.rmdir()
                    except:
                        break
                    parent = parent.parent

        except Exception as e:
            logger.error(f"Error deleting file {file_path}: {e}")
    
    def _on_error(self, ws, error):
        # Don't log connection errors - they're handled in _on_close
        # Only log unexpected errors
        error_str = str(error)
        if self.running and "Connection to remote host was lost" not in error_str:
            logger.error(f"WebSocket error: {error}")
    
    def _on_close(self, ws, close_status_code, close_msg):
        if self.running:
            inactive_time = datetime.now() - self.last_activity
            if inactive_time > timedelta(seconds=self.hibernation_timeout):
                self._save_state(ws)

            click.echo(f"Connection lost. Reconnecting in {self.reconnect_delay} seconds...")
            time.sleep(self.reconnect_delay)

            self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)

            if self.running:
                self._connect()
    
    def _save_state(self, ws):
        try:
            # Skip save_state for now to avoid server error
            # state = {
            #     "last_sync": self.last_activity.isoformat(),
            #     "prefix": self.sync_handler.prefix
            # }

            # save_message = json.dumps({
            #     "type": "save_state",
            #     "state": state
            # })

            # if ws.sock and ws.sock.connected:
            #     ws.send(save_message)
            pass
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
    
    def _connect(self):
        try:
            # Construct the WebSocket URL for the API gateway
            # The API gateway expects the format: wss://domain/api/cli/sync/{projectId}
            websocket_url = f"{self.websocket_url}/api/cli/sync/{self.project_id}"

            # Suppress websocket library's own error logging
            websocket_logger = logging.getLogger('websocket')
            websocket_logger.setLevel(logging.CRITICAL)

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
            # Configure SSL context with proper certificate verification
            ssl_context = ssl.create_default_context()
            ssl_context.load_verify_locations(certifi.where())
            
            # Use run_forever with ping_interval and ping_timeout for better connection handling
            # Also include origin and host headers for proper WebSocket upgrade
            self.ws_app.run_forever(
                ping_interval=self.ping_interval,
                ping_timeout=10,
                ping_payload='{"type": "ping"}',
                origin=None,  # Let the library handle origin
                host=None,    # Let the library handle host
                sslopt={"context": ssl_context}  # Use proper SSL context
            )
        except ssl.SSLError as ssl_error:
            if self.running:
                logger.error(f"SSL certificate verification failed: {ssl_error}")
                click.echo(f"Connection error. Reconnecting in {self.reconnect_delay} seconds...")
                time.sleep(self.reconnect_delay)
                if self.running:
                    self._connect()
        except Exception as e:
            if self.running:
                logger.error(f"WebSocket connection error: {e}")
                click.echo(f"Connection error. Reconnecting in {self.reconnect_delay} seconds...")
                time.sleep(self.reconnect_delay)
                if self.running:
                    self._connect()
    
    def start(self):
        if self.running:
            return

        self.running = True

        try:
            # Enable progress output for initial sync
            downloaded, updated, deleted = self.sync_handler.sync()

            # Show summary if there were any changes
            if downloaded or updated or deleted:
                click.echo(f"\nInitial sync complete: {len(downloaded)} new, {len(updated)} updated, {len(deleted)} deleted")
        except Exception as e:
            logger.error(f"Initial sync failed: {e}")

        self._connect()

    def stop(self):
        self.running = False

        if self.ws_app:
            self.ws_app.close()
            self.ws_app = None