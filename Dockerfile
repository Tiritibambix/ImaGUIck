# Choisir l'image de base
FROM python:3.11-slim

# Dépendances nécessaires pour compiler ImageMagick et autres utilitaires
RUN apt-get update && apt-get install -y \
    imagemagick \
    libmagickwand-dev \
    exiftool \
    build-essential \
    wget \
    tar \
    libjpeg-dev \
    libpng-dev \
    libtiff-dev \
    libgif-dev \
    libx11-dev \
    libxt-dev \
    zip unzip \
    && rm -rf /var/lib/apt/lists/*

# Télécharger et installer ImageMagick 7.1.1-41
RUN wget https://github.com/ImageMagick/ImageMagick/archive/refs/tags/7.1.1-41.tar.gz -O /tmp/imagemagick.tar.gz \
    && tar -xvzf /tmp/imagemagick.tar.gz -C /tmp \
    && cd /tmp/ImageMagick-7.1.1-41 \
    && ./configure --prefix=/usr/local --disable-shared --without-x \
    && make -j4 \
    && make install \
    && rm -rf /tmp/*

# Configure ImageMagick policy to allow PDF operations
COPY policy.xml /etc/ImageMagick-6/policy.xml

# Ajouter /usr/local/bin au PATH
ENV PATH="/usr/local/bin:${PATH}"

# Vérifier que ImageMagick est bien installé
RUN magick -version

# Set up app directory
WORKDIR /app

# Copier l'application dans le conteneur
COPY . /app

# Installer les dépendances Python
RUN pip install --no-cache-dir -r /app/requirements.txt

# Create upload and output directories
RUN mkdir -p uploads outputs

# Set environment variables
ENV FLASK_APP=app.py
ENV FLASK_ENV=production

# Exposer le port
EXPOSE 5000

# Commande pour démarrer l'application Flask
CMD ["flask", "run", "--host=0.0.0.0"]
