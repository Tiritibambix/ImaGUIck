#!/bin/bash
set -e

echo "Starting cleanup..."

# Démarrer le service cron
service cron start || echo "Warning: Could not start cron service"

# Créer les répertoires si nécessaire
mkdir -p /app/uploads
mkdir -p /app/output

# Trouver le chemin de Gunicorn
GUNICORN_PATH=$(which gunicorn || echo "/usr/local/bin/gunicorn")

if [ ! -f "$GUNICORN_PATH" ]; then
    echo "Error: Gunicorn not found in PATH"
    GUNICORN_PATH="/usr/local/python/bin/gunicorn"
fi

echo "Using Gunicorn at: $GUNICORN_PATH"

# Démarrer l'application avec Gunicorn
exec $GUNICORN_PATH --bind 0.0.0.0:5000 --workers 4 --timeout 120 app:app
