FROM python:3.9-slim

# Installer les dépendances système (ImageMagick)
RUN apt-get update && apt-get install -y \
    imagemagick \
    && rm -rf /var/lib/apt/lists/*

# Installer Flask et les autres dépendances Python
WORKDIR /app
COPY . /app
RUN pip install -r requirements.txt

# Exposer le port Flask
EXPOSE 5000

# Commande de démarrage
CMD ["python", "app.py"]
