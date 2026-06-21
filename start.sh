#!/bin/bash
set -e

echo "Starting cleanup service configuration..."

# Check/create the log file
if [ ! -f /var/log/cleanup.log ]; then
    touch /var/log/cleanup.log
    chmod 666 /var/log/cleanup.log
fi

# Start the cron service with detailed logging
if ! service cron start > /var/log/cron.log 2>&1; then
    echo "Error: Failed to start cron service"
    cat /var/log/cron.log
    exit 1
fi

# Check that cron is actually running
if ! pgrep cron > /dev/null; then
    echo "Error: Cron service is not running"
    exit 1
fi

# Check that the task is correctly scheduled
if ! crontab -l | grep -q cleanup.py; then
    echo "Error: Cleanup task not found in crontab"
    exit 1
fi

echo "Cron service started and validated successfully"

# Create the directories if needed and ensure correct permissions
mkdir -p /app/uploads && chmod 755 /app/uploads
mkdir -p /app/output && chmod 755 /app/output

# Find the Gunicorn path
GUNICORN_PATH=$(which gunicorn || echo "/usr/local/bin/gunicorn")

if [ ! -f "$GUNICORN_PATH" ]; then
    echo "Error: Gunicorn not found in PATH"
    GUNICORN_PATH="/usr/local/python/bin/gunicorn"
fi

echo "Using Gunicorn at: $GUNICORN_PATH"

# Start the application with Gunicorn
exec $GUNICORN_PATH --bind 0.0.0.0:5000 --workers 4 --worker-class gthread --threads 8 --timeout 600 --limit-request-line 8190 app:app
