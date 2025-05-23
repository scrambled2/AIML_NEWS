import os
import json
import logging
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class Config:
    def __init__(self, config_path='config.json', env_path='.env'):
        """Initialize configuration from config.json and .env files."""
        # Load environment variables
        load_dotenv(env_path)
        
        self.config = self._load_config(config_path)
        self.api_key = os.getenv('OPENAI_API_KEY')
        self.database_path = os.getenv('DATABASE_PATH', 'instance/aiml_news.db')
        
        # Ensure required environment variables are set
        if not self.api_key and self.config.get('store_content_level') != 'none':
            logger.warning("OPENAI_API_KEY not found in environment variables. LLM processing will not be available.")
    
    def _load_config(self, config_path):
        """Load configuration from JSON file."""
        try:
            if not os.path.exists(config_path):
                logger.warning(f"Config file not found: {config_path}. Using default values.")
                return self._get_default_config()
                
            with open(config_path, 'r') as f:
                config = json.load(f)
                
            logger.info(f"Loaded configuration from: {config_path}")
            return config
        except json.JSONDecodeError:
            logger.error(f"Error parsing config file: {config_path}. Using default values.")
            return self._get_default_config()
        except Exception as e:
            logger.error(f"Error loading config: {e}. Using default values.")
            return self._get_default_config()
    
    def _get_default_config(self):
        """Return default configuration values."""
        return {
            "polling_interval_minutes": 30,
            "max_concurrent_feeds": 5,
            "store_content_level": "summary_only",
            "openai_model": "gpt-4o",
            "summary_max_tokens": 150
        }
    
    def get(self, key, default=None):
        """Get configuration value by key."""
        return self.config.get(key, default)
    
    def save_config(self, config_path='config.json'):
        """Save current configuration to file."""
        try:
            with open(config_path, 'w') as f:
                json.dump(self.config, f, indent=4)
            logger.info(f"Saved configuration to: {config_path}")
        except Exception as e:
            logger.error(f"Error saving config: {e}")