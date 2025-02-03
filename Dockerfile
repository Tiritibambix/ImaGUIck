# Choisir l'image de base
FROM python:3.9-slim

# Installer les dépendances nécessaires pour compiler ImageMagick et autres utilitaires
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc-10 \
    g++-10 \
    wget \
    tar \
    pkg-config \
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
    && update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-10 100 \
    && rm -rf /var/lib/apt/lists/*

# Télécharger et compiler ImageMagick 7.1.1-41
RUN cd /tmp \
    && wget https://github.com/ImageMagick/ImageMagick/archive/refs/tags/7.1.1-41.tar.gz -O imagemagick.tar.gz \
    && tar xzf imagemagick.tar.gz \
    && cd ImageMagick-7.1.1-41 \
    && ./configure \
        --prefix=/usr/local \
        --disable-shared \
        --without-x \
    && make -j$(nproc) || make -j1 \
    && make install \
    && ldconfig /usr/local/lib \
    && cd /tmp \
    && rm -rf * \
    && magick -version

# Ajouter /usr/local/bin au PATH
ENV PATH="/usr/local/bin:${PATH}"

# Vérifier que ImageMagick est bien installé
RUN magick -version

# Copier l'application dans le conteneur
WORKDIR /app
COPY . /app

# Vérifier que cleanup.py et cleanup.sh existent avant de les rendre exécutables
RUN test -f /app/cleanup.py && chmod +x /app/cleanup.py || echo "cleanup.py manquant"
RUN test -f /app/cleanup.sh && chmod +x /app/cleanup.sh || echo "cleanup.sh manquant"

# Configurer le cron job correctement
RUN echo "0 */12 * * * /usr/local/bin/python /app/cleanup.py >> /var/log/cleanup.log 2>&1" > /etc/cron.d/cleanup-cron \
    && chmod 0644 /etc/cron.d/cleanup-cron \
    && crontab /etc/cron.d/cleanup-cron

# Installer les dépendances Python depuis requirements.txt
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Script de démarrage pour lancer cron et l'application
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Exposer le port
EXPOSE 5000

# Utiliser le script de démarrage
CMD ["/app/start.sh"]
