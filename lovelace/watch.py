import json
import logging
import time
import threading
import ssl
import certifi
import click
from typing import Dict, Optional, Callable, Set
from datetime import datetime, timedelta
from pathlib import Path
import websocket
from websocket import WebSocketApp
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent
from .sync import R2Sync

logger = logging.getLogger(__name__)

class WatchError(Exception):
    pass

class FileSystemWatcher(FileSystemEventHandler):
    """Watches local file system for changes and uploads them to R2"""

    def __init__(self, sync_handler: R2Sync, in_flight_operations: Set[str]):
        super().__init__()
        self.sync_handler = sync_handler
        self.in_flight_operations = in_flight_operations
        self.observer = Observer()
        self.debounce_timers: Dict[str, threading.Timer] = {}
        self.debounce_delay = 1.0  # Wait 1 second before uploading
        self.lock = threading.Lock()

    def _should_ignore_path(self, path: str) -> bool:
        """Check if path should be ignored"""
        path_obj = Path(path)

        # Ignore .lovelace config file
        if path_obj.name == '.lovelace':
            return True

        # Ignore hidden directories and files
        for part in path_obj.parts:
            if part.startswith('.') and part != '.':
                return True

        # Ignore temporary files (check both suffix and if .tmp appears in name)
        if path_obj.suffix in ['.tmp', '.swp', '.swx', '.swpx']:
            return True

        # Ignore files with .tmp anywhere in the name (e.g., testing.tmp.XXXXX)
        if '.tmp' in path_obj.name:
            return True

        return False

    def _get_relative_path(self, path: str) -> str:
        """Get path relative to local root"""
        return str(Path(path).relative_to(self.sync_handler.local_root))

    def _get_remote_key(self, relative_path: str) -> str:
        """Construct remote key from relative path"""
        if self.sync_handler.prefix:
            prefix = self.sync_handler.prefix.rstrip('/')
            return f"{prefix}/{relative_path}"
        return relative_path

    def _handle_file_change(self, path: str):
        """Handle file created or modified event with debouncing"""
        if self._should_ignore_path(path):
            return

        try:
            relative_path = self._get_relative_path(path)

            # Check if file is being downloaded
            if relative_path in self.in_flight_operations:
                logger.debug(f"Ignoring change to {relative_path} (in-flight operation)")
                return

            # Cancel existing timer for this file
            with self.lock:
                if relative_path in self.debounce_timers:
                    self.debounce_timers[relative_path].cancel()

                # Create new debounced upload timer
                timer = threading.Timer(
                    self.debounce_delay,
                    self._upload_file,
                    args=[path, relative_path]
                )
                self.debounce_timers[relative_path] = timer
                timer.start()

        except Exception as e:
            logger.error(f"Error handling file change for {path}: {e}")

    def _upload_file(self, path: str, relative_path: str):
        """Upload file to R2 storage"""
        try:
            # Remove from debounce timers
            with self.lock:
                self.debounce_timers.pop(relative_path, None)

            # Double-check we should not ignore this file (in case it changed since queued)
            if self._should_ignore_path(path):
                logger.debug(f"Skipping upload of ignored file: {relative_path}")
                return

            # Mark as in-flight to avoid circular operations
            self.in_flight_operations.add(relative_path)

            try:
                local_path = Path(path)

                # Check if file still exists (might have been deleted/renamed during debounce)
                if not local_path.exists():
                    logger.debug(f"File no longer exists, skipping upload: {relative_path}")
                    return

                remote_key = self._get_remote_key(relative_path)

                # Disable progress output temporarily
                old_show_progress = self.sync_handler.show_progress
                self.sync_handler.show_progress = False
                success = self.sync_handler._upload_file(local_path, remote_key)
                self.sync_handler.show_progress = old_show_progress

                if success:
                    click.echo(f"  ↑ Uploaded {relative_path}")

            finally:
                # Remove from in-flight operations
                self.in_flight_operations.discard(relative_path)

        except Exception as e:
            logger.error(f"Error uploading file {relative_path}: {e}")
            self.in_flight_operations.discard(relative_path)

    def _handle_file_delete(self, path: str):
        """Handle file deleted event"""
        if self._should_ignore_path(path):
            return

        try:
            relative_path = self._get_relative_path(path)

            # Check if file is being operated on
            if relative_path in self.in_flight_operations:
                logger.debug(f"Ignoring delete of {relative_path} (in-flight operation)")
                return

            # Cancel any pending upload timer
            with self.lock:
                if relative_path in self.debounce_timers:
                    self.debounce_timers[relative_path].cancel()
                    self.debounce_timers.pop(relative_path, None)

            # Mark as in-flight
            self.in_flight_operations.add(relative_path)

            try:
                remote_key = self._get_remote_key(relative_path)

                # Disable progress output temporarily
                old_show_progress = self.sync_handler.show_progress
                self.sync_handler.show_progress = False
                success = self.sync_handler._delete_remote_file(remote_key)
                self.sync_handler.show_progress = old_show_progress

                if success:
                    click.echo(f"  ↑ Deleted from remote: {relative_path}")

            finally:
                self.in_flight_operations.discard(relative_path)

        except Exception as e:
            logger.error(f"Error deleting remote file {relative_path}: {e}")
            self.in_flight_operations.discard(relative_path)

    def on_created(self, event: FileSystemEvent):
        """Handle file created event"""
        if not event.is_directory:
            self._handle_file_change(event.src_path)

    def on_modified(self, event: FileSystemEvent):
        """Handle file modified event"""
        if not event.is_directory:
            self._handle_file_change(event.src_path)

    def on_deleted(self, event: FileSystemEvent):
        """Handle file deleted event"""
        if not event.is_directory:
            self._handle_file_delete(event.src_path)

    def start(self):
        """Start watching the local directory"""
        self.observer.schedule(
            self,
            str(self.sync_handler.local_root),
            recursive=True
        )
        self.observer.start()
        logger.info("Local file system watcher started")

    def stop(self):
        """Stop watching the local directory"""
        # Cancel all pending timers
        with self.lock:
            for timer in self.debounce_timers.values():
                timer.cancel()
            self.debounce_timers.clear()

        self.observer.stop()
        self.observer.join()
        logger.info("Local file system watcher stopped")

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

        # Track in-flight operations to avoid circular sync
        self.in_flight_operations: Set[str] = set()

        # Initialize file system watcher for local changes
        self.fs_watcher = FileSystemWatcher(sync_handler, self.in_flight_operations)
        
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
            # Normalize the path (remove leading slash for consistency)
            normalized_path = file_path.lstrip('/')

            # Construct the remote key the same way the sync command does
            # The remote key should be the full S3 key including the prefix
            if self.sync_handler.prefix:
                # Remove trailing slash from prefix and leading slash from file_path
                prefix = self.sync_handler.prefix.rstrip('/')
                remote_key = f"{prefix}/{normalized_path}"
            else:
                remote_key = normalized_path

            local_path = self.sync_handler.local_root / normalized_path

            # Mark as in-flight to prevent local watcher from uploading (use normalized path)
            self.in_flight_operations.add(normalized_path)

            try:
                # Disable progress output for individual file downloads
                old_show_progress = self.sync_handler.show_progress
                self.sync_handler.show_progress = False
                success = self.sync_handler._download_file(remote_key, local_path)
                self.sync_handler.show_progress = old_show_progress

                if success and not normalized_path.endswith('.gitkeep'):
                    action = "Created" if change_type == "created" else "Updated"
                    click.echo(f"  ✓ {action} {normalized_path}")

                # Keep in-flight flag for 2 seconds to allow file system events to settle
                # This prevents the FileSystemWatcher from re-uploading the file we just downloaded
                def remove_in_flight():
                    time.sleep(2)
                    self.in_flight_operations.discard(normalized_path)

                cleanup_thread = threading.Thread(target=remove_in_flight, daemon=True)
                cleanup_thread.start()

            except Exception as e:
                logger.error(f"Error syncing file {normalized_path}: {e}")
                self.in_flight_operations.discard(normalized_path)

        except Exception as e:
            logger.error(f"Error syncing file {file_path}: {e}")
            self.in_flight_operations.discard(file_path.lstrip('/'))
    
    def _handle_file_delete(self, file_path: str):
        try:
            # Normalize the path (remove leading slash for consistency)
            normalized_path = file_path.lstrip('/')

            local_path = self.sync_handler.local_root / normalized_path

            # Mark as in-flight to prevent local watcher from deleting remote (use normalized path)
            self.in_flight_operations.add(normalized_path)

            try:
                if local_path.exists():
                    local_path.unlink()
                    if not normalized_path.endswith('.gitkeep'):
                        click.echo(f"  ✓ Deleted {normalized_path}")

                    parent = local_path.parent
                    while parent != self.sync_handler.local_root:
                        try:
                            if not any(parent.iterdir()):
                                parent.rmdir()
                        except:
                            break
                        parent = parent.parent

                # Keep in-flight flag for 2 seconds to allow file system events to settle
                def remove_in_flight():
                    time.sleep(2)
                    self.in_flight_operations.discard(normalized_path)

                cleanup_thread = threading.Thread(target=remove_in_flight, daemon=True)
                cleanup_thread.start()

            except Exception as e:
                logger.error(f"Error deleting file {normalized_path}: {e}")
                self.in_flight_operations.discard(normalized_path)

        except Exception as e:
            logger.error(f"Error deleting file {file_path}: {e}")
            self.in_flight_operations.discard(file_path.lstrip('/'))
    
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

        # Start the WebSocket connection for remote-to-local sync
        self._connect()

        # Start the file system watcher for local-to-remote sync
        try:
            self.fs_watcher.start()
            click.echo("Two-way sync enabled: watching for local file changes")
        except Exception as e:
            logger.error(f"Failed to start file system watcher: {e}")

    def stop(self):
        self.running = False

        # Stop file system watcher
        try:
            self.fs_watcher.stop()
        except Exception as e:
            logger.error(f"Error stopping file system watcher: {e}")

        # Stop WebSocket connection
        if self.ws_app:
            self.ws_app.close()
            self.ws_app = None