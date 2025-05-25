# file : config.py

import os
from dotenv import load_dotenv

# Explicitly load .env file from project root
load_dotenv('.env')  

class Settings:
    """Essential configuration with clear environment loading"""
    
    # Required Azure credentials (will raise KeyError if missing)
    AZURE_VISION_ENDPOINT = os.environ['AZURE_VISION_ENDPOINT']
    AZURE_VISION_KEY = os.environ['AZURE_VISION_KEY']
    
    # Optional with default
    TEMPLATE_PATH = os.environ.get('TEMPLATE_PATH', 'templates/medical_template.xlsx')

# Instantiate (will fail immediately if required vars are missing)
settings = Settings()