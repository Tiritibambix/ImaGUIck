FROM python:3.9-slim

# Installer les dépendances système (ImageMagick et les outils nécessaires)
RUN apt-get update && apt-get install -y \
    imagemagick \
    imagemagick-common \
    libmagickcore-6.q16-6-extra \
    && rm -rf /var/lib/apt/lists/*

# Vérifier l'installation de magick
RUN which magick || (echo "magick not found" && exit 1)
RUN magick -version

# Installer Flask et les autres dépendances Python
WORKDIR /app
COPY . /app
RUN pip install -r requirements.txt

# Exposer le port Flask
EXPOSE 5000

# Commande de démarrage
CMD ["python", "app.py"]
