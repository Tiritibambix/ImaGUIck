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

# Start the application with Gunicorn.
# Exactly one worker process: app.py keeps all state (jobs, upload_sessions,
# the ImageMagick concurrency semaphore, the WebP-support cache) in plain
# in-memory Python objects with no external store. Those are only shared
# between threads of the SAME process, not across separate worker processes —
# with more than one worker, a request can land on a worker that never saw
# the upload_sessions/jobs entry a previous request created on another worker,
# causing spurious "No files selected" / "Job not found" errors. Concurrency
# still comes from --threads within this single process; the ImageMagick
# invocation limit is enforced by _processing_semaphore (BoundedSemaphore(4))
# in app.py, which is only correct when there is one process.
exec $GUNICORN_PATH --bind 0.0.0.0:5000 --workers 1 --worker-class gthread --threads 16 --timeout 600 --limit-request-line 8190 app:app
