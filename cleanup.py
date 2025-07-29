#!/usr/bin/env python3
import os
import time
import logging
from datetime import datetime, timedelta

# Configuration
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'output'
MAX_AGE_HOURS = 48

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='/var/log/cleanup.log',
    filemode='a'
)

def cleanup_folders():
    """Remove files older than MAX_AGE_HOURS from uploads and output folders."""
    now = datetime.now()
    folders = [UPLOAD_FOLDER, OUTPUT_FOLDER]
    
    for folder in folders:
        if not os.path.exists(folder):
            logging.warning(f"Folder {folder} does not exist")
            continue
            
        logging.info(f"Starting cleanup of {folder}")
        for filename in os.listdir(folder):
            filepath = os.path.join(folder, filename)
            if os.path.isfile(filepath):
                mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                age = now - mtime
                
                if age > timedelta(hours=MAX_AGE_HOURS):
                    try:
                        os.remove(filepath)
                        logging.info(f"Removed {filepath} (age: {age})")
                    except Exception as e:
                        logging.error(f"Error removing {filepath}: {e}")

if __name__ == '__main__':
    cleanup_folders()
