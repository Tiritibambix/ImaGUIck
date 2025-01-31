#!/bin/bash
set -e

echo "🚀 Démarrage du script start.sh"

# Démarrer le service cron en arrière-plan
echo "🔄 Démarrage du service cron..."
cron -f &

# Création des répertoires nécessaires
echo "📂 Vérification et création des répertoires..."
mkdir -p /app/uploads /app/output

# Trouver le chemin de Gunicorn
GUNICORN_PATH=$(command -v gunicorn || true)

if [ -z "$GUNICORN_PATH" ]; then
    echo "❌ Erreur : Gunicorn introuvable ! Vérifiez l'installation."
    exit 1
fi

echo "✅ Gunicorn trouvé : $GUNICORN_PATH"

# Démarrer l'application avec Gunicorn
echo "🚀 Lancement de Gunicorn..."
exec "$GUNICORN_PATH" --bind 0.0.0.0:5000 --workers 4 --timeout 120 app:app
