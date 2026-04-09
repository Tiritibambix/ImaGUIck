# Base image
FROM --platform=$BUILDPLATFORM python:3.9-slim

# Target architecture (amd64 or arm64)
ARG TARGETARCH

# Install system dependencies
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
    potrace \
    zip \
    unzip \
    cron \
    procps \
    && cjxl --version \
    && djxl --version \
    && rm -rf /var/lib/apt/lists/*


# ARM64: use the pre-compiled apt package; AMD64: build from source for JXL support
RUN if [ "$TARGETARCH" = "arm64" ]; then \
        echo "Using pre-compiled ImageMagick for ARM64"; \
        apt-get update && apt-get install -y imagemagick; \
    else \
        echo "Building ImageMagick from source for AMD64"; \
        wget https://github.com/ImageMagick/ImageMagick/archive/refs/tags/7.1.2-18.tar.gz -O /tmp/imagemagick.tar.gz && \
        tar -xvzf /tmp/imagemagick.tar.gz -C /tmp && \
        cd /tmp/ImageMagick-7.1.2-18 && \
        ./configure --prefix=/usr/local --disable-shared --without-x --disable-openmp --with-jxl && \
        make -j$(nproc) && \
        make install && \
        rm -rf /tmp/*; \
    fi

# Ensure /usr/local/bin is on PATH (source-compiled binaries land there)
ENV PATH="/usr/local/bin:${PATH}"

# Verify ImageMagick is correctly installed
RUN magick -version

# Copy application source
WORKDIR /app
COPY . /app

# Make helper scripts executable
RUN chmod +x /app/cleanup.py /app/cleanup.sh

# Set up cleanup cron job (runs every 12 hours, logs to /var/log/cleanup.log)
RUN echo "0 */12 * * * root cd /app && /usr/local/bin/python /app/cleanup.py >> /var/log/cleanup.log 2>&1" > /etc/cron.d/cleanup-cron
RUN chmod 0644 /etc/cron.d/cleanup-cron
RUN crontab /etc/cron.d/cleanup-cron

# Create log file with appropriate permissions
RUN touch /var/log/cleanup.log && \
    chmod 666 /var/log/cleanup.log

# Install Python dependencies
RUN pip install --no-cache-dir -r /app/requirements.txt

# Install and verify Gunicorn
RUN pip install gunicorn && \
    gunicorn --version && \
    which gunicorn

# Copy and enable the entrypoint script (starts cron + Gunicorn)
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

EXPOSE 5000

CMD ["/app/start.sh"]