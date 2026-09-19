<p align="center">
  <img src="https://raw.githubusercontent.com/tiritibambix/ImaGUIck/refs/heads/main/static/media/imaguick-banner-opacity.png" width="400" alt="ImaGUIck" />
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Platform-amd64%20%7C%20arm64-blue" alt="Platform Support" />
  <a href="https://github.com/Tiritibambix/ImaGUIck/actions/workflows/docker-build.yml">
    <img src="https://github.com/Tiritibambix/ImaGUIck/actions/workflows/docker-build.yml/badge.svg" alt="Build and Push Docker Image">
  </a>
  <img src="https://img.shields.io/badge/UI-no%20build%20step-8b5cf6" alt="No build step" />
</p>

<p align="center">
  A self-hosted web interface for image resizing, format conversion, and animated GIF/WEBP creation — powered by ImageMagick, with no accounts, no database, and no tracking.
</p>

---

## ⚠️ Security notice

This application has been coded with the help of AI and is designed for **local or trusted-network use only**. It has no built-in authentication. Exposing it to the public internet without an additional access-control layer (reverse proxy with auth, VPN, etc.) is done at your own risk.

---

## Features

### Resize & convert

- **Single and batch processing** — handle one image or hundreds at once
- **Flexible resizing** — by exact dimensions, percentage, or one-click presets (1080p / 1920p) with optional aspect-ratio lock
- **Wide format support**
  - Common: JPG, PNG, GIF, BMP, TIFF, WEBP
  - RAW: ARW, CR2, CR3, NEF, RAF, RW2, DNG
  - Modern: AVIF, HEIC, JXL
  - Animation: GIF, WEBP, APNG
  - Vector / document: SVG, PDF, EPS (requires `potrace`)
- **Image enhancement** — auto-level, auto-gamma, and three-level unsharp masking (low / standard / high)
- **Smart format recommendations** — context-aware suggestions based on image type and transparency
- **URL import** — fetch and process an image directly from a URL
- **Real-time progress** — per-file status streamed via Server-Sent Events (SSE) during batch jobs
- **Automatic ZIP export** — processed batch files packaged and ready to download

### Animated GIF / WEBP

- **Create** an animation from a sequence of images — drag to reorder frames, set FPS, loop count, and an optional shared canvas size, output as GIF or WEBP
- **Edit** an existing animated GIF/WEBP:
  - Resize (by dimensions or percentage)
  - Optimize (palette size, Floyd–Steinberg dithering)
  - Change playback speed
  - Reverse
  - Rotate / flip
  - Change loop count
  - Extract a single frame, a frame range, or every frame (as PNG or WEBP, zipped when extracting more than one)
- Animated WEBP output is automatically offered or hidden depending on whether the server's ImageMagick build actually supports WEBP muxing — no dead options in the UI

### Housekeeping

- **Automatic cleanup** — uploaded and output files purged after 48 hours; completed batch/GIF jobs purged from memory after 2 hours

## Screenshots

<!-- TODO: these were captured against an earlier version of the UI (pre-redesign) — regenerate against the current interface, and consider adding a GIF-creation screenshot. -->

![Upload](https://raw.githubusercontent.com/tiritibambix/ImaGUIck/refs/heads/main/screenshots/Upload.webp)

![Options](https://raw.githubusercontent.com/tiritibambix/ImaGUIck/refs/heads/main/screenshots/Options.webp)

![Results](https://raw.githubusercontent.com/tiritibambix/ImaGUIck/refs/heads/main/screenshots/Results.webp)

---

## Upload limits

| Limit | Value |
|---|---|
| Total request size | 2 GB |
| Per-file maximum | 200 MB |
| Maximum image dimension | 10 000 px per side |
| Maximum GIF/WEBP canvas dimension | 4 000 px per side |
| Maximum frames per animation | 500 |
| Concurrent ImageMagick workers | 4 (semaphore-controlled) |

Batch uploads and GIF/WEBP creation are both processed **asynchronously** — the browser redirects to a live progress page immediately after the transfer completes, and each item shows its own status (queued / processing / done / error) via SSE. A ZIP archive is created automatically for batch resizes and multi-frame extractions.

---

## Installation

### Prerequisites

| Dependency | Version | Notes |
|---|---|---|
| Python | 3.9+ | |
| [ImageMagick](https://github.com/ImageMagick/ImageMagick/releases/tag/7.1.2-18) | 7.1.2-18+ | Add to PATH on Windows; install `libmagickwand-dev` on Linux |
| ExifTool | any | Required for RAW metadata |
| potrace | any | Required for vector output (SVG, EPS, PDF) |
| libwebp (+ pkg-config) | any | Required for animated WEBP creation/editing — single-frame WEBP works without it |
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
potrace --version  # required for SVG/EPS/PDF output
magick -list delegate | grep -i webp   # confirms animated WEBP support
```

Start the server:

```bash
python app.py
```

The application is available at `http://localhost:5000`.

> **Note:** The local installation runs a cleanup task that removes files older than 48 hours. Trigger it manually with `python cleanup.py --now`.

---

## Usage

### Resize or convert an image

1. Open `http://localhost:5000` in your browser.
2. Select your import method:
   - **Upload** — drag-and-drop or file picker (single file or batch, folders accepted)
   - **URL** — paste a direct image URL
3. Configure processing options: output format, resize mode (dimensions, percentage, or preset), and enhancement options (auto-level, auto-gamma, sharpening level).
4. Submit — for batches, a live progress page tracks each file in real time.
5. Download the result or ZIP archive when processing completes.

### Create an animated GIF/WEBP

1. On the upload page, switch to the **Create GIF · WEBP** tab.
2. Select at least two images — drag the rows to set the frame order.
3. Upload, then set FPS, loop count, an optional shared canvas size, palette size / quality, and output format (GIF or WEBP).
4. Submit — a live progress page tracks the build, then offers the animation for download.

### Edit an existing animation

From the resize options page of any animated GIF/WEBP you've uploaded, follow the **Edit as animation** link, pick an operation (resize, optimize, speed, reverse, rotate/flip, loop count, or frame extraction), and apply it.

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
| Image processing | ImageMagick 7.1.2-18, ExifTool, Pillow, potrace |
| Async pipeline | `ThreadPoolExecutor` + `BoundedSemaphore(4)` — no external queue required |
| Progress streaming | Server-Sent Events (SSE) via `/job/<id>/status` |
| Frontend | Vanilla HTML / CSS / JavaScript, zero build step (dark theme, DM Sans + DM Mono, inline SVG icon sprite) |
| Container | Docker (multi-arch: amd64 + arm64) |

### Project structure

```
imaguick/
├── Dockerfile                        # Multi-arch container build
├── docker-compose.yml                # Compose deployment example
├── start.sh                          # Container entrypoint (cron + Gunicorn)
├── app.py                            # Flask application — routes and processing logic
├── cleanup.py                        # File cleanup script (stdout logging, Docker-compatible)
├── cleanup.sh                        # Manual cleanup helper
├── requirements.txt                  # Python dependencies
├── templates/
│   ├── base.html                     # Design system: CSS variables, header/nav, SVG icon sprite
│   ├── index.html                    # Upload page — Resize / Create GIF·WEBP tabs
│   ├── resize.html                   # Single-image resize options
│   ├── resize_batch.html             # Batch resize options
│   ├── gif_create.html               # Create an animation from a sequence of images
│   ├── gif_edit.html                 # Edit an existing animated GIF/WEBP
│   ├── progress.html                 # Real-time job progress (SSE) — batch resize and GIF creation
│   ├── result.html                   # Success / error feedback
│   ├── _resize_options_styles.html   # Shared CSS partial for options-page layouts
│   └── _resize_form_fields.html      # Shared Jinja macros for repeated form fields
└── static/                           # Fonts, images, favicon
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

GIF/WEBP creation reuses this same job/SSE machinery as a single unit of work (one ImageMagick invocation over the ordered frame list) rather than one task per file.

### Security

- All filenames sanitised with `werkzeug.utils.secure_filename` at route entry
- Path traversal prevented by `secure_path()` — confines all file access to `uploads/` and `output/`
- Output formats validated against an explicit allowlist (`ALLOWED_OUTPUT_FORMATS`)
- Sharpen level validated against `ALLOWED_SHARPEN_LEVELS`
- Vector output formats checked for `potrace` availability before building the ImageMagick command
- Resize/GIF dimensions are capped (`MAX_DIMENSION`, `GIF_MAX_OUTPUT_DIMENSION`) on both input **and** requested output, and GIF creation enforces a maximum frame count and combined pixel budget before any processing starts
- SSRF prevented by `is_safe_url()` — DNS resolution + rejection of private/loopback/link-local IPs
- Every subprocess call uses list-form arguments (never `shell=True`) and an explicit timeout
- GitHub Actions workflows use minimal `permissions: contents: read` and SHA-pinned actions

### Customisation

- **Supported formats** — edit `get_available_formats()` in `app.py`
- **Resize options** — extend `build_imagemagick_command()` in `app.py`
- **GIF/WEBP creation or editing** — extend `build_gif_create_command()` / `build_gif_edit_command()` / `build_gif_extract_command()` in `app.py`
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
