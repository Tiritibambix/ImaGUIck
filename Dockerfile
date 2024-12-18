# Utiliser une image de base avec Python
FROM python:3.9-slim

# Installer les dépendances du système, y compris ImageMagick
RUN apt-get update && apt-get install -y \
    imagemagick \
    tcl \
    tk \
    && rm -rf /var/lib/apt/lists/*

# Définir le répertoire de travail
WORKDIR /app

# Copier les fichiers de l'application
COPY . /app

# Installer les dépendances Python
RUN pip install --no-cache-dir -r requirements.txt

# Exposer l'application pour l'exécution
CMD ["python", "app.py"]
