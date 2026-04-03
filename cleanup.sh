#!/bin/bash

# ATTENTION : ce script supprime TOUS les fichiers des dossiers uploads/ et output/,
# quelle que soit leur date. Utilisé manuellement uniquement.
echo "WARNING: This will delete ALL files in uploads/ and output/ regardless of age."
echo "Press Ctrl+C within 5 seconds to cancel."
sleep 5

/usr/local/bin/python /app/cleanup.py --all
