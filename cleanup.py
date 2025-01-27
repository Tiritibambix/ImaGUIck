#!/usr/bin/env python3
import os
import time
from datetime import datetime, timedelta
import logging

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def cleanup_old_files(directory, hours=48):
    """
    Nettoie les fichiers plus vieux que le nombre d'heures spécifié
    """
    if not os.path.exists(directory):
        logging.warning(f"Le répertoire {directory} n'existe pas")
        return

    cutoff = time.time() - (hours * 3600)
    total_size_freed = 0
    files_removed = 0

    logging.info(f"Début du nettoyage de {directory}")
    
    for root, dirs, files in os.walk(directory, topdown=False):
        # D'abord nettoyer les fichiers
        for name in files:
            filepath = os.path.join(root, name)
            try:
                stats = os.stat(filepath)
                if stats.st_mtime < cutoff:
                    size = stats.st_size
                    os.remove(filepath)
                    total_size_freed += size
                    files_removed += 1
                    logging.info(f"Supprimé: {filepath}")
            except Exception as e:
                logging.error(f"Erreur lors de la suppression de {filepath}: {e}")

        # Ensuite essayer de supprimer les répertoires vides
        for name in dirs:
            dirpath = os.path.join(root, name)
            try:
                if not os.listdir(dirpath):  # Si le répertoire est vide
                    os.rmdir(dirpath)
                    logging.info(f"Supprimé répertoire vide: {dirpath}")
            except Exception as e:
                logging.error(f"Erreur lors de la suppression du répertoire {dirpath}: {e}")

    logging.info(f"Nettoyage terminé: {files_removed} fichiers supprimés, "
                f"{total_size_freed / (1024*1024):.2f} MB libérés")

if __name__ == "__main__":
    # Nettoyer les dossiers uploads et output
    cleanup_old_files("uploads")
    cleanup_old_files("output")
