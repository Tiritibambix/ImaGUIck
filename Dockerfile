# Build stage
FROM python:3.9-slim as builder

# Install build dependencies
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
    dcraw \
    zip unzip \
    && rm -rf /var/lib/apt/lists/*

# Build ImageMagick
RUN wget https://github.com/ImageMagick/ImageMagick/archive/refs/tags/7.1.1-41.tar.gz -O /tmp/imagemagick.tar.gz \
    && tar -xzf /tmp/imagemagick.tar.gz -C /tmp \
    && cd /tmp/ImageMagick-7.1.1-41 \
    && ./configure --prefix=/usr/local --disable-shared --without-x \
    && make -j$(nproc) \
    && make install \
    && rm -rf /tmp/*

# Final stage
FROM python:3.9-slim

# Copy ImageMagick from builder
COPY --from=builder /usr/local /usr/local

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
    exiftool \
    && rm -rf /var/lib/apt/lists/*

# Add /usr/local/bin to PATH
ENV PATH="/usr/local/bin:${PATH}"

# Verify ImageMagick installation
RUN magick -version

# Set up application
WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . /app

# Copy ImageMagick delegates configuration
COPY delegates.xml /etc/ImageMagick-6/delegates.xml

EXPOSE 5000
CMD ["python", "app.py"]
