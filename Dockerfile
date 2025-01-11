# Build stage
FROM python:3.9-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libmagickcore-dev \
    libmagickwand-dev \
    && rm -rf /var/lib/apt/lists/*

# Final stage
FROM python:3.9-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    libmagickcore-dev \
    libmagickwand-dev \
    dcraw \
    zip \
    unzip \
    libjpeg62-turbo \
    libpng16-16 \
    libtiff-dev \
    libgif7 \
    && rm -rf /var/lib/apt/lists/*

# Add /usr/local/bin to PATH
ENV PATH="/usr/local/bin:${PATH}"

# Set up application
WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . /app

EXPOSE 5000
CMD ["python", "app.py"]
