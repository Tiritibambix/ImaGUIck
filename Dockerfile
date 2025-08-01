# Choisir l'image de base
FROM --platform=$BUILDPLATFORM python:3.9-slim

# Détecter l'architecture (amd64 ou arm64)
ARG TARGETARCH

# Installer les dépendances nécessaires
RUN apt-get update && apt-get install -y \
    build-essential \
    g++ \
    autoconf \
    automake \
    libtool \
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
    libjxl-tools \
    libjxl-dev \
    exiftool \
    zip \
    unzip \
    cron \
    procps \
    && cjxl --version \
    && djxl --version \
    && rm -rf /var/lib/apt/lists/*


# Cas particulier pour ARM64 : utiliser une version pré-compilée d'ImageMagick
RUN if [ "$TARGETARCH" = "arm64" ]; then \
        echo "Using pre-compiled ImageMagick for ARM64"; \
        apt-get update && apt-get install -y imagemagick; \
    else \
        echo "Building ImageMagick from source for AMD64"; \
        wget https://github.com/ImageMagick/ImageMagick/archive/refs/tags/7.1.1-41.tar.gz -O /tmp/imagemagick.tar.gz && \
        tar -xvzf /tmp/imagemagick.tar.gz -C /tmp && \
        cd /tmp/ImageMagick-7.1.1-41 && \
        ./configure --prefix=/usr/local --disable-shared --without-x --disable-openmp --with-jxl && \
        make -j$(nproc) && \
        make install && \
        rm -rf /tmp/*; \
    fi

# Ajouter /usr/local/bin au PATH
ENV PATH="/usr/local/bin:${PATH}"

# Vérifier que ImageMagick est bien installé
RUN magick -version

# Copier l'application dans le conteneur
WORKDIR /app
COPY . /app

# Rendre les scripts exécutables
RUN chmod +x /app/cleanup.py /app/cleanup.sh

# Configurer le cron job
# Configurer le cron job avec logging approprié
RUN echo "0 */12 * * * root cd /app && /usr/local/bin/python /app/cleanup.py >> /var/log/cleanup.log 2>&1" > /etc/cron.d/cleanup-cron
RUN chmod 0644 /etc/cron.d/cleanup-cron
RUN crontab /etc/cron.d/cleanup-cron

# Créer le fichier de log avec les bonnes permissions
RUN touch /var/log/cleanup.log && \
    chmod 666 /var/log/cleanup.log

# Installer les dépendances Python
RUN pip install --no-cache-dir -r /app/requirements.txt

# Vérifier l'installation de Gunicorn
RUN pip install gunicorn && \
    gunicorn --version && \
    which gunicorn

# Script de démarrage pour lancer cron et l'application
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Exposer le port
EXPOSE 5000

# Utiliser le script de démarrage
CMD ["/app/start.sh"]
