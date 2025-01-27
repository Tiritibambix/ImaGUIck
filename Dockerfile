# Choisir l'image de base
FROM python:3.9-slim

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
    cron \
    && rm -rf /var/lib/apt/lists/*

# Télécharger et installer ImageMagick 7.1.1-41
RUN wget https://github.com/ImageMagick/ImageMagick/archive/refs/tags/7.1.1-41.tar.gz -O /tmp/imagemagick.tar.gz \
    && tar -xvzf /tmp/imagemagick.tar.gz -C /tmp \
    && cd /tmp/ImageMagick-7.1.1-41 \
    && ./configure --prefix=/usr/local --disable-shared --without-x \
    && make \
    && make install \
    && rm -rf /tmp/*

# Ajouter /usr/local/bin au PATH
ENV PATH="/usr/local/bin:${PATH}"

# Vérifier que ImageMagick est bien installé
RUN magick -version

# Copier l'application dans le conteneur
WORKDIR /app
COPY . /app

# Rendre le script de nettoyage exécutable
RUN chmod +x /app/cleanup.py

# Configurer le cron job
RUN echo "0 */12 * * * /usr/local/bin/python /app/cleanup.py >> /var/log/cleanup.log 2>&1" > /etc/cron.d/cleanup-cron
RUN chmod 0644 /etc/cron.d/cleanup-cron
RUN crontab /etc/cron.d/cleanup-cron

# Installer les dépendances Python
RUN pip install --no-cache-dir -r /app/requirements.txt

# Script de démarrage pour lancer cron et l'application
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Exposer le port
EXPOSE 5000

# Utiliser le script de démarrage
CMD ["/app/start.sh"]
