FROM python:3.9-slim

# Ajouter le dépôt d'ImageMagick
RUN apt-get update && apt-get install -y \
    software-properties-common \
    && add-apt-repository ppa:graphicsmagick/imagemagick \
    && apt-get update

# Installer la version spécifique d'ImageMagick
RUN apt-get install -y \
    imagemagick=7.1.1-41 \
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
