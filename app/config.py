import os
from typing import Dict, Any
import yaml

class ConfigManager:
    def __init__(self, config_path: str = 'config/databases.yaml'):
        self.config_path = config_path
        self.configs = self._load_configs()
        
    def _load_configs(self) -> Dict[str, Any]:
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f)
        return {}
        
    def get_active_database(self) -> str:
        """Get the active database name from environment variables."""
        return os.getenv('DEFAULT_DB_NAME', 'default')
        
    def get_database_config(self, name: str = None) -> Dict[str, Any]:
        """Get database config, using environment variable if name is not specified."""
        if name is None:
            name = self.get_active_database()
        return self.configs.get(name, {}) 