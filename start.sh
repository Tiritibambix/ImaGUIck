#!/bin/bash
set -e

echo "Starting cleanup..."

# Démarrer le service cron et vérifier qu'il fonctionne
if ! service cron start; then
    echo "Error: Failed to start cron service"
    exit 1
fi

# Vérifier que cron est bien en cours d'exécution
if ! pgrep cron > /dev/null; then
    echo "Error: Cron service is not running"
    exit 1
fi

echo "Cron service started successfully"

# Créer les répertoires si nécessaire et s'assurer des bonnes permissions
mkdir -p /app/uploads && chmod 755 /app/uploads
mkdir -p /app/output && chmod 755 /app/output

# Trouver le chemin de Gunicorn
GUNICORN_PATH=$(which gunicorn || echo "/usr/local/bin/gunicorn")

if [ ! -f "$GUNICORN_PATH" ]; then
    echo "Error: Gunicorn not found in PATH"
    GUNICORN_PATH="/usr/local/python/bin/gunicorn"
fi

echo "Using Gunicorn at: $GUNICORN_PATH"

# Démarrer l'application avec Gunicorn
exec $GUNICORN_PATH --bind 0.0.0.0:5000 --workers 4 --timeout 120 app:app
