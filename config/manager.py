import os
import yaml
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

class ConfigManager:
    """
    Singleton class to manage configuration settings.
    Loads settings.yaml only once into memory.
    """
    _instance = None
    _config: Dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance._load_config()
            cls._instance._setup_logging()
        return cls._instance

    def _setup_logging(self):
        """Sets up centralized logging with a RotatingFileHandler."""
        from logging.handlers import RotatingFileHandler
        
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        log_dir = os.path.join(project_root, "logs")
        os.makedirs(log_dir, exist_ok=True)
        
        log_file = os.path.join(log_dir, "bistbot.log")
        
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        
        # Remove existing handlers to avoid duplicates
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
            
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        
        # File Handler (Max 5MB, keeps 3 backups)
        file_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
        
        # Console Handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
        
        logger.info("Merkezi loglama sistemi baslatildi. Log dosyasi: %s", log_file)

    def _load_config(self):
        """Loads the configuration from settings.yaml or settings.example.yaml."""
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cfg_path = os.path.join(project_root, "config", "settings.yaml")
        
        if not os.path.exists(cfg_path):
            cfg_path = os.path.join(project_root, "config", "settings.example.yaml")
            logger.warning(f"settings.yaml not found. Using {cfg_path}")
            
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                self._config = yaml.safe_load(f) or {}
            logger.info("Configuration loaded successfully into memory.")
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            self._config = {}

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value by key.
        Returns default if key is not found.
        """
        return self._config.get(key, default)
    
    def get_all(self) -> Dict[str, Any]:
        """Returns the entire configuration dictionary."""
        return self._config

# Global instance for easy access
config = ConfigManager()
