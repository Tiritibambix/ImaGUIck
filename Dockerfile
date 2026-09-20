# Base image. Do NOT pin this to $BUILDPLATFORM: buildx then bakes the builder's
# architecture into every target image, so the arm64 manifest entry would ship
# amd64 binaries.
FROM python:3.9-slim

ARG IMAGEMAGICK_VERSION=7.1.2-31

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    g++ \
    autoconf \
    automake \
    libtool \
    pkg-config \
    wget \
    tar \
    libjpeg-dev \
    libpng-dev \
    libtiff-dev \
    libgif-dev \
    libx11-dev \
    libxt-dev \
    libjxl-tools \
    libjxl-dev \
    libwebp-dev \
    exiftool \
    dcraw \
    potrace \
    zip \
    unzip \
    cron \
    procps \
    && cjxl --version \
    && djxl --version \
    && dcraw 2>&1 | head -1 \
    && rm -rf /var/lib/apt/lists/*


# Build ImageMagick from source on every architecture. Debian's `imagemagick`
# package is ImageMagick 6, which ships no `magick` binary at all — and this app
# calls `magick` exclusively — so an apt path for arm64 was never viable.
RUN wget "https://github.com/ImageMagick/ImageMagick/archive/refs/tags/${IMAGEMAGICK_VERSION}.tar.gz" -O /tmp/imagemagick.tar.gz && \
    tar -xzf /tmp/imagemagick.tar.gz -C /tmp && \
    cd "/tmp/ImageMagick-${IMAGEMAGICK_VERSION}" && \
    ./configure --prefix=/usr/local --disable-shared --without-x --with-jxl && \
    make -j$(nproc) && \
    make install && \
    rm -rf /tmp/*

# Ensure /usr/local/bin is on PATH (source-compiled binaries land there)
ENV PATH="/usr/local/bin:${PATH}"

# Bound ImageMagick's resource use. THREAD_LIMIT matters because the build now
# has OpenMP enabled: the app already caps concurrent ImageMagick processes at 4
# (BoundedSemaphore), so leaving threads unbounded would oversubscribe the CPU.
# Memory and map limits are deliberately left to ImageMagick's own host-based
# detection; override any of these in docker-compose.yml if needed.
ENV MAGICK_THREAD_LIMIT=4 \
    MAGICK_AREA_LIMIT=512MP \
    MAGICK_DISK_LIMIT=8GiB

# Fail the build on a wrong or missing tarball rather than shipping it
RUN magick -version | grep -q "ImageMagick ${IMAGEMAGICK_VERSION}"

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