# Choisir l'image de base
FROM python:3.9-slim

# Créer un utilisateur non-root
RUN groupadd -r imagick && useradd -r -g imagick imagick

# Dépendances nécessaires pour compiler ImageMagick et autres utilitaires
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
    libmagickcore-dev \
    libmagickwand-dev \
    exiftool \
    zip unzip \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Télécharger et installer ImageMagick 7.1.1-41
RUN wget https://github.com/ImageMagick/ImageMagick/archive/refs/tags/7.1.1-41.tar.gz -O /tmp/imagemagick.tar.gz \
    && tar -xvzf /tmp/imagemagick.tar.gz -C /tmp \
    && cd /tmp/ImageMagick-7.1.1-41 \
    && ./configure --prefix=/usr/local --disable-shared --without-x \
    --with-security-policy=/etc/ImageMagick-7/policy.xml \
    && make \
    && make install \
    && rm -rf /tmp/*

# Configurer la politique de sécurité d'ImageMagick
COPY policy.xml /etc/ImageMagick-7/policy.xml

# Ajouter /usr/local/bin au PATH
ENV PATH="/usr/local/bin:${PATH}"

# Vérifier que ImageMagick est bien installé
RUN magick -version

# Créer et définir les permissions des répertoires
RUN mkdir -p /app/uploads /app/output \
    && chown -R imagick:imagick /app

# Copier l'application dans le conteneur
WORKDIR /app
COPY --chown=imagick:imagick . /app

# Installer les dépendances Python
RUN pip install --no-cache-dir -r /app/requirements.txt

# Exposer le port
EXPOSE 5000

# Passer à l'utilisateur non-root
USER imagick

# Variables d'environnement pour la sécurité
ENV FLASK_ENV=production \
    PYTHONUNBUFFERED=1 \
    FLASK_SECRET_KEY=""

# Commande pour démarrer l'application Flask
CMD ["python", "app.py"]
