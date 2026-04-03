#!/usr/bin/env python3
import os
import sys
import glob
import shutil
import logging
import argparse
from datetime import datetime, timedelta

# Configuration
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'output'
MAX_AGE_HOURS = 48
ORPHAN_BATCH_AGE_HOURS = 2

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout
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
                    logging.info(f"Removed empty directory {dirpath}")
                except OSError as e:
                    logging.error(f"Could not remove directory {dirpath}: {e}")

    cleanup_orphan_batch_dirs(now, remove_all)
    cleanup_jxl_tmp_files()


def cleanup_orphan_batch_dirs(now, remove_all=False):
    """Remove batch_* directories that were not finalised (no corresponding ZIP or older than ORPHAN_BATCH_AGE_HOURS)."""
    if not os.path.exists(OUTPUT_FOLDER):
        return

    for name in os.listdir(OUTPUT_FOLDER):
        if not name.startswith('batch_'):
            continue
        batch_path = os.path.join(OUTPUT_FOLDER, name)
        if not os.path.isdir(batch_path):
            continue
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(batch_path))
            age = now - mtime
            if remove_all or age > timedelta(hours=ORPHAN_BATCH_AGE_HOURS):
                shutil.rmtree(batch_path, ignore_errors=True)
                logging.info(f"Removed orphan batch dir {batch_path} (age: {age})")
        except Exception as e:
            logging.error(f"Error removing batch dir {batch_path}: {e}")


def cleanup_jxl_tmp_files():
    """Remove leftover imaguick JXL temp files from /tmp."""
    for tmp_file in glob.glob('/tmp/imaguick_*.png'):
        try:
            os.remove(tmp_file)
            logging.info(f"Removed temp JXL file {tmp_file}")
        except Exception as e:
            logging.error(f"Could not remove temp JXL file {tmp_file}: {e}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Cleanup old files from uploads and output folders.')
    parser.add_argument('--all', action='store_true', help='Remove all files, regardless of age.')
    args = parser.parse_args()

    cleanup_folders(remove_all=args.all)
