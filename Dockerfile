# Choisir l'image de base
FROM python:3.9-slim

# Dépendances nécessaires pour compiler ImageMagick et d'autres utilitaires
RUN apt-get update && apt-get install -y \
    build-essential \
    wget \
    tar \
    libjpeg-dev \
    libpng-dev \
    libtiff-dev \
    libgif-dev \
    libx11-dev \
    libxt-dev \
    && rm -rf /var/lib/apt/lists/*

# Télécharger et installer ImageMagick 7.1.1-41
RUN wget https://github.com/ImageMagick/ImageMagick/archive/refs/tags/7.1.1-41.tar.gz -O /tmp/imagemagick.tar.gz \
    && tar -xvzf /tmp/imagemagick.tar.gz -C /tmp \
    && cd /tmp/ImageMagick-7.1.1-41 \
    && ./configure --prefix=/usr/local \
    && make \
    && make install \
    && rm -rf /tmp/*

# Vérifier que ImageMagick est bien installé
RUN magick -version

# Copier l'application dans le conteneur
WORKDIR /app
COPY . /app

# Installer les dépendances Python
RUN pip install --no-cache-dir -r /app/requirements.txt

# Exposer le port
EXPOSE 5000

# Commande pour démarrer l'application Flask
CMD ["python", "app.py"]
