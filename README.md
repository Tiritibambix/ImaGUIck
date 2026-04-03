<p align="center">
  <img src="https://raw.githubusercontent.com/tiritibambix/ImaGUIck/refs/heads/main/static/media/imaguick-banner-opacity.png" width="400" alt="ImaGUIck" />
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Platform-amd64%20%7C%20arm64-blue" alt="Platform Support" />
  <a href="https://github.com/tiritibambix/ImaGUIck/actions/workflows/github-code-scanning/codeql">
    <img src="https://github.com/tiritibambix/ImaGUIck/actions/workflows/github-code-scanning/codeql/badge.svg" alt="CodeQL">
  </a>
  <a href="https://github.com/Tiritibambix/ImaGUIck/actions/workflows/docker-build.yml">
    <img src="https://github.com/Tiritibambix/ImaGUIck/actions/workflows/docker-build.yml/badge.svg" alt="Build and Push Docker Image">
  </a>
  <a href="https://github.com/Tiritibambix/ImaGUIck/actions/workflows/docker-build-AMD64.yml">
    <img src="https://github.com/Tiritibambix/ImaGUIck/actions/workflows/docker-build-AMD64.yml/badge.svg" alt="Build and Push Docker Image (AMD64)">
  </a>
</p>

<p align="center">
  A self-hosted web interface for batch image resizing and format conversion, powered by ImageMagick.
</p>

---

## Features

- **Single and batch processing** — handle one image or hundreds at once
- **Flexible resizing** — by exact dimensions, percentage, or one-click presets (1080p / 1920p) with optional aspect-ratio lock
- **Wide format support**
  - Common: JPG, PNG, GIF, BMP, TIFF, WEBP
  - RAW: ARW, CR2, CR3, NEF, RAF, RW2, DNG
  - Modern: AVIF, HEIC, JXL
  - Animation: GIF, WEBP, APNG
  - Vector / document: SVG, PDF, EPS
- **Image enhancement** — auto-level, auto-gamma, and three-level unsharp masking (low / standard / high)
- **Smart format recommendations** — context-aware suggestions based on image type and transparency
- **URL import** — fetch and process an image directly from a URL
- **Real-time progress** — per-file status streamed via Server-Sent Events (SSE) during batch jobs
- **Automatic ZIP export** — processed batch files packaged and ready to download
- **Automatic cleanup** — uploaded and output files purged after 48 hours

## Screenshots

![Landing page](https://raw.githubusercontent.com/tiritibambix/ImaGUIck/refs/heads/main/screenshots/ImaGUIck_1.png)

![Resize](https://raw.githubusercontent.com/tiritibambix/ImaGUIck/refs/heads/main/screenshots/ImaGUIck_2.png)

---

## Upload limits

| Limit | Value |
|---|---|
| Total request size | 2 GB |
| Per-file maximum | 200 MB |
| Maximum image dimension | 10 000 px per side |
| Concurrent ImageMagick workers | 4 (semaphore-controlled) |

Batch uploads are processed **asynchronously** — the browser redirects to a live progress page immediately after the transfer completes. Each file shows its own status (queued / processing / done / error) via SSE. A ZIP archive is created automatically once all files finish.

---

## ⚠️ Security notice

This application is designed for **local or trusted-network use only**. It has no built-in authentication. Exposing it to the public internet without an additional access-control layer (reverse proxy with auth, VPN, etc.) is done at your own risk.

---

## Installation

### Prerequisites

| Dependency | Version | Notes |
|---|---|---|
| Python | 3.9+ | |
| [ImageMagick](https://github.com/ImageMagick/ImageMagick/releases/tag/7.1.2-18) | 7.1.2-18+ | Add to PATH on Windows; install `libmagickwand-dev` on Linux |
| ExifTool | any | Required for RAW metadata |
| Docker | any | Recommended deployment method |

### Docker (recommended)

**Option 1 — Docker Compose**

Create a `docker-compose.yml`:

```yaml
services:
  imaguick:
    stdin_open: true
    tty: true
    volumes:
      - ./uploads:/app/uploads
      - ./output:/app/output
    ports:
      - 5000:5000
    image: tiritibambix/imaguick:latest
    environment:
      - FLASK_SECRET_KEY=${FLASK_SECRET_KEY:-change-me-in-production}
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:5000/health', timeout=5)"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
networks: {}
```

Then run:

```bash
docker compose up -d
```

**Option 2 — docker run**

```bash
docker run -it --rm \
    -v $(pwd)/uploads:/app/uploads \
    -v $(pwd)/output:/app/output \
    -e FLASK_SECRET_KEY=change-me-in-production \
    -p 5000:5000 \
    tiritibambix/imaguick:latest
```

**Option 3 — build from source**

```bash
git clone https://github.com/tiritibambix/ImaGUIck.git
cd ImaGUIck
docker build -t imaguick .
docker run -it --rm \
    -v $(pwd)/uploads:/app/uploads \
    -v $(pwd)/output:/app/output \
    -p 5000:5000 \
    imaguick
```

### Local installation

```bash
git clone https://github.com/tiritibambix/ImaGUIck.git
cd ImaGUIck
mkdir -p uploads output
pip install -r requirements.txt
```

Verify dependencies:

```bash
magick -version    # ImageMagick 7.1.2-18 or newer
exiftool -ver
```

Start the server:

```bash
python app.py
```

The application is available at `http://localhost:5000`.

> **Note:** The local installation runs a cleanup task that removes files older than 48 hours. Trigger it manually with `python cleanup.py --now`.

---

## Usage

1. Open `http://localhost:5000` in your browser.
2. Select your import method:
   - **Upload** — drag-and-drop or file picker (single file or batch)
   - **URL** — paste a direct image URL
3. Configure processing options:
   - Output format
   - Resize mode (dimensions, percentage, or preset)
   - Enhancement options (auto-level, auto-gamma, sharpening)
4. Submit — for batches, a live progress page tracks each file in real time.
5. Download the result or ZIP archive when processing completes.

---

## File cleanup

| Method | Command |
|---|---|
| Automatic (every 12 h, files > 48 h) | Runs via cron inside the container |
| Manual — files older than 48 h | `docker exec <container> /app/cleanup.sh` |
| Manual — all files immediately | `docker exec <container> /app/cleanup.sh --all` |

---

## Technical architecture

### Stack

| Layer | Technology |
|---|---|
| Backend | Flask (Python 3.9+), Gunicorn (gthread, 4 workers × 8 threads) |
| Image processing | ImageMagick 7.1.2-18, ExifTool, Pillow |
| Async pipeline | `ThreadPoolExecutor` + `BoundedSemaphore(4)` — no external queue required |
| Progress streaming | Server-Sent Events (SSE) via `/job/<id>/status` |
| Frontend | Vanilla HTML / CSS / JavaScript |
| Container | Docker (multi-arch: amd64 + arm64) |

### Project structure

```
imaguick/
├── Dockerfile                  # Multi-arch container build
├── docker-compose.yml          # Compose deployment example
├── start.sh                    # Container entrypoint (cron + Gunicorn)
├── app.py                      # Flask application — routes and processing logic
├── cleanup.py                  # File cleanup script (stdout logging, Docker-compatible)
├── cleanup.sh                  # Manual cleanup helper
├── requirements.txt            # Python dependencies
├── templates/
│   ├── base.html               # Shared layout
│   ├── index.html              # Upload page
│   ├── resize.html             # Single-image options
│   ├── resize_batch.html       # Batch options
│   ├── progress.html           # Real-time batch progress (SSE)
│   └── result.html             # Success / error feedback
└── static/                     # CSS, images, favicon
```

### Batch processing pipeline

```
Browser                     Flask (Gunicorn)              ThreadPoolExecutor
  │                               │                              │
  ├─ POST /upload ──────────────> │                              │
  │                               │  save files, create job      │
  │ <─ {redirect: /progress} ─── │  submit tasks ─────────────> │
  │                               │                              │ acquire semaphore (max 4)
  ├─ GET /job/<id>/status (SSE) > │                              │ run ImageMagick
  │ <─ {file, status, pct} ────── │ <── update job dict ──────── │ release semaphore
  │ <─ {complete, zip} ─────────  │                              │
  ├─ GET /download_batch/<zip> ─> │                              │
```

### Customisation

- **Supported formats** — edit `get_available_formats()` in `app.py`
- **Processing options** — extend `build_imagemagick_command()` in `app.py`
- **Secret key** — set the `FLASK_SECRET_KEY` environment variable (required in production)

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit your changes: `git commit -m 'Add my feature'`
4. Push: `git push origin feature/my-feature`
5. Open a pull request

---

## License

This project is licensed under the **GNU General Public License v3.0** — see the [LICENSE](LICENSE) file for details.

ImageMagick is licensed separately — see the [ImageMagick license](https://imagemagick.org/script/license.php).

---

<p align="center">Made with ❤️ in Python</p>
