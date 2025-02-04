# Choisir l'image de base
FROM python:3.9-slim

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
    exiftool \
    zip unzip \
    cron \
    && rm -rf /var/lib/apt/lists/*

# Définir une variable d'environnement pour améliorer la compatibilité QEMU
ENV QEMU_EXECVE=1
ENV CFLAGS="-O1"
ENV CXXFLAGS="-O1"

# Télécharger et installer ImageMagick 7.1.1-41
RUN wget https://github.com/ImageMagick/ImageMagick/archive/refs/tags/7.1.1-41.tar.gz -O /tmp/imagemagick.tar.gz \
    && tar -xvzf /tmp/imagemagick.tar.gz -C /tmp \
    && cd /tmp/ImageMagick-7.1.1-41 \
    && ./configure --prefix=/usr/local --disable-shared --without-x --disable-openmp \
    && make -j2 \
    && make install \
    && rm -rf /tmp/*

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
RUN echo "0 */12 * * * /usr/local/bin/python /app/cleanup.py >> /var/log/cleanup.log 2>&1" > /etc/cron.d/cleanup-cron
RUN chmod 0644 /etc/cron.d/cleanup-cron
RUN crontab /etc/cron.d/cleanup-cron

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
