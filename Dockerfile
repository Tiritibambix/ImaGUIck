FROM python:3.9-slim

# Installer les dépendances nécessaires pour ImageMagick
RUN apt-get update && apt-get install -y \
    wget \
    libmagickcore-6.q16-6-extra \
    && rm -rf /var/lib/apt/lists/*

# Télécharger et installer ImageMagick 7.1.1-41
RUN wget https://download.imagemagick.org/ImageMagick/download/ImageMagick-7.1.1-41.tar.gz \
    && tar -xzvf ImageMagick-7.1.1-41.tar.gz \
    && cd ImageMagick-7.1.1-41 \
    && ./configure \
    && make \
    && make install \
    && ldconfig /usr/local/lib \
    && cd .. \
    && rm -rf ImageMagick-7.1.1-41 ImageMagick-7.1.1-41.tar.gz

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
