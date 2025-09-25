import subprocess
import sys
import logging
import requests
from typing import Optional, Tuple
from packaging import version
from . import __version__

logger = logging.getLogger(__name__)

class UpgradeError(Exception):
    pass

class Upgrader:
    def __init__(self, package_name: str = "lovelace", 
                 pypi_url: str = "https://pypi.org/pypi/{}/json",
                 upgrade_url: Optional[str] = None):
        self.package_name = package_name
        self.pypi_url = pypi_url.format(package_name)
        self.upgrade_url = upgrade_url
        self.current_version = __version__
    
    def get_latest_version(self) -> Optional[str]:
        try:
            if self.upgrade_url:
                response = requests.get(self.upgrade_url, timeout=10)
                response.raise_for_status()
                data = response.json()
                return data.get("version")
            else:
                response = requests.get(self.pypi_url, timeout=10)
                response.raise_for_status()
                data = response.json()
                return data.get("info", {}).get("version")
                
        except requests.RequestException as e:
            logger.error(f"Failed to check for updates: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error checking for updates: {e}")
            return None
    
    def compare_versions(self, latest: str) -> Tuple[bool, str, str]:
        try:
            current = version.parse(self.current_version)
            latest_ver = version.parse(latest)
            
            needs_update = latest_ver > current
            
            return needs_update, str(current), str(latest_ver)
            
        except Exception as e:
            logger.error(f"Failed to compare versions: {e}")
            return False, self.current_version, latest
    
    def perform_upgrade(self) -> bool:
        try:
            logger.info(f"Upgrading {self.package_name}...")
            
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", self.package_name],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                logger.info("Upgrade completed successfully")
                return True
            else:
                logger.error(f"Upgrade failed: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("Upgrade timed out after 5 minutes")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during upgrade: {e}")
            return False
    
    def check_and_upgrade(self, force: bool = False) -> Tuple[bool, str]:
        logger.info("Checking for updates...")
        
        latest_version = self.get_latest_version()
        if not latest_version:
            return False, "Failed to check for updates"
        
        needs_update, current, latest = self.compare_versions(latest_version)
        
        if not needs_update and not force:
            message = f"Already running the latest version ({current})"
            logger.info(message)
            return False, message
        
        if force:
            logger.info(f"Force upgrading from {current} to {latest}")
        else:
            logger.info(f"New version available: {latest} (current: {current})")
        
        success = self.perform_upgrade()
        
        if success:
            message = f"Successfully upgraded from {current} to {latest}"
            logger.info(message)
            return True, message
        else:
            message = f"Failed to upgrade to version {latest}"
            logger.error(message)
            return False, message