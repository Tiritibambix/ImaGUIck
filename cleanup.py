#!/usr/bin/env python3
import os
import time
import logging
from datetime import datetime, timedelta

# Configuration
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'output'
import argparse

MAX_AGE_HOURS = 48

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='/var/log/cleanup.log',
    filemode='a'
)

def cleanup_folders(remove_all=False):
    """Remove files older than MAX_AGE_HOURS from uploads and output folders."""
    now = datetime.now()
    folders = [UPLOAD_FOLDER, OUTPUT_FOLDER]
    
    for folder in folders:
        if not os.path.exists(folder):
            logging.warning(f"Folder {folder} does not exist")
            continue
            
        logging.info(f"Starting cleanup of {folder}")
        for root, dirs, files in os.walk(folder, topdown=False):
            for name in files:
                filepath = os.path.join(root, name)
                mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                age = now - mtime

                if remove_all or age > timedelta(hours=MAX_AGE_HOURS):
                    try:
                        os.remove(filepath)
                        logging.info(f"Removed {filepath} (age: {age})")
                    except Exception as e:
                        logging.error(f"Error removing {filepath}: {e}")

            for name in dirs:
                dirpath = os.path.join(root, name)
                try:
                    os.rmdir(dirpath)
                    logging.info(f"Removed directory {dirpath}")
                except OSError as e:
                    logging.error(f"Error removing directory {dirpath}: {e}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Cleanup old files from uploads and output folders.')
    parser.add_argument('--all', action='store_true', help='Remove all files, regardless of age.')
    args = parser.parse_args()

    cleanup_folders(remove_all=args.all)
