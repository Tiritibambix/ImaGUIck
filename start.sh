#!/bin/bash

# Démarrer le service cron
service cron start

# Créer les répertoires si nécessaire
mkdir -p /app/uploads
mkdir -p /app/output

# Démarrer l'application avec Gunicorn
exec gunicorn --bind 0.0.0.0:5000 --workers 4 --timeout 120 app:app
