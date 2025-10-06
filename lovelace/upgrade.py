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
                 github_repo: str = "lovelace-sh/lovelace-cli",
                 upgrade_url: Optional[str] = None):
        self.package_name = package_name
        self.github_repo = github_repo
        self.github_api_url = f"https://api.github.com/repos/{github_repo}/releases/latest"
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
                # Check GitHub releases for latest version
                response = requests.get(self.github_api_url, timeout=10)
                response.raise_for_status()
                data = response.json()
                tag_name = data.get("tag_name", "")
                # Strip 'v' prefix if present
                return tag_name.lstrip("v") if tag_name else None

        except requests.RequestException as e:
            logger.debug(f"Failed to check for updates: {e}")
            return None
        except Exception as e:
            logger.debug(f"Unexpected error checking for updates: {e}")
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
            # Install from GitHub
            install_url = f"git+https://github.com/{self.github_repo}.git"
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", install_url],
                capture_output=True,
                text=True,
                timeout=300
            )

            if result.returncode == 0:
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
    
    def check_for_update(self) -> Tuple[bool, Optional[str], Optional[str]]:
        """Check if an update is available. Returns (needs_update, current_version, latest_version)"""
        latest_version = self.get_latest_version()
        if not latest_version:
            return False, self.current_version, None

        needs_update, current, latest = self.compare_versions(latest_version)
        return needs_update, current, latest

    def check_and_upgrade(self, force: bool = False) -> Tuple[bool, str]:
        latest_version = self.get_latest_version()
        if not latest_version:
            return False, "Failed to check for updates"

        needs_update, current, latest = self.compare_versions(latest_version)

        if not needs_update and not force:
            message = f"Already running the latest version ({current})"
            return False, message

        success = self.perform_upgrade()

        if success:
            message = f"Successfully upgraded from {current} to {latest}"
            return True, message
        else:
            message = f"Failed to upgrade to version {latest}"
            return False, message