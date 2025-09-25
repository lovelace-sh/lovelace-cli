import os
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

CONFIG_FILE = ".lovelace"

class ConfigError(Exception):
    pass

class ConfigManager:
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path.cwd() / CONFIG_FILE
        self.config_data = {}
    
    def load(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            raise ConfigError(f"Configuration file not found: {self.config_path}")
        
        try:
            with open(self.config_path, 'r') as f:
                self.config_data = json.load(f)
            
            return self.config_data
        except json.JSONDecodeError as e:
            raise ConfigError(f"Invalid configuration file format: {e}")
        except Exception as e:
            raise ConfigError(f"Failed to load configuration: {e}")
    
    def save(self, config: Dict[str, Any]) -> None:
        try:
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            # Set restrictive permissions for security
            os.chmod(self.config_path, 0o600)
            
            self.config_data = config
            logger.info(f"Configuration saved to {self.config_path}")
            
        except Exception as e:
            raise ConfigError(f"Failed to save configuration: {e}")
    
    def exists(self) -> bool:
        return self.config_path.exists()
    
    def delete(self) -> None:
        if self.config_path.exists():
            self.config_path.unlink()
            logger.info(f"Configuration file deleted: {self.config_path}")
    
    def get(self, key: str, default=None):
        if not self.config_data:
            self.load()
        return self.config_data.get(key, default)
    
    def update(self, updates: Dict[str, Any]) -> None:
        if not self.config_data:
            self.load()
        self.config_data.update(updates)
        self.save(self.config_data)