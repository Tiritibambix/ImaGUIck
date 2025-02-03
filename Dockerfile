# Choisir l'image de base
FROM python:3.9-slim

# Installer les dépendances nécessaires pour compiler ImageMagick et autres utilitaires
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
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
    && rm -rf /var/lib/apt/lists/*

# Télécharger et compiler ImageMagick 7.1.1-41
RUN cd /tmp \
    && wget https://github.com/ImageMagick/ImageMagick/archive/refs/tags/7.1.1-41.tar.gz 
