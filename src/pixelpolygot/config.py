import os
import json

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")
DEFAULT_CONFIG = {
    "api_type": "openai",
    "api_url": "http://localhost:9009/v1",
    "api_key": "<YOUR_API_KEY_HERE>", # Moved api_key after api_url
    "model": "qwen2.5-vl-7b-instruct",
    "prompt": "What is the Japanese text in this image and what does it mean in English?",
    "watch_directory": "",
}


def load_config():
    """Loads configuration from file or returns defaults."""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                # Ensure all default keys are present
                config = DEFAULT_CONFIG.copy()
                loaded_config = json.load(f)
                config.update(loaded_config)
                return config
        else:
            return DEFAULT_CONFIG.copy()
    except Exception as e:
        print(f"Error loading config: {e}")
        return DEFAULT_CONFIG.copy()


def save_config(config):
    """Saves configuration to file."""
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)  # Add indent for readability
    except Exception as e:
        print(f"Error saving config: {e}")