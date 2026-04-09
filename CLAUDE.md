# CLAUDE.md

This file provides context for Claude when working on this codebase.

---

## Project overview

ImaGUIck is a self-hosted Flask web application for single and batch image resizing and format conversion, powered by ImageMagick. It is deployed via Docker (multi-arch: amd64 + arm64) and published on Docker Hub as `tiritibambix/imaguick`.

---

## Repository structure

```
app.py                  # All Flask routes and image processing logic
cleanup.py              # Scheduled file cleanup (48 h retention)
cleanup.sh              # Manual cleanup helper script
Dockerfile              # Multi-arch Docker build (amd64 compiled from source, arm64 via apt)
docker-compose.yml      # Reference deployment
start.sh                # Container entrypoint: starts cron + Gunicorn
requirements.txt        # Python deps (Flask, Pillow, requests)
templates/
  base.html             # Design system: CSS variables, shared components, DM Sans + DM Mono fonts
  index.html            # Upload page (drag-and-drop, XHR upload with progress bar, URL import)
  resize.html           # Single-image resize options
  resize_batch.html     # Batch resize options
  progress.html         # Real-time SSE progress page for batch jobs
  result.html           # Success / error result page
static/media/           # Logo, banner, favicon
.github/workflows/
  docker-build.yml      # CI/CD: build + push multi-arch image to Docker Hub (main branch)
  docker-build-test.yml # CI/CD: build + push test image (test branch)
```

---

## Architecture decisions

### Backend

- **Flask + Gunicorn** (gthread worker, 4 workers × 8 threads)
- **No database** — job state held in-memory in the `jobs` dict (protected by `jobs_lock`)
- **Async batch processing** via `ThreadPoolExecutor` (16 workers) + `BoundedSemaphore(4)` for ImageMagick concurrency
- **SSE streaming** — `/job/<id>/status` polls the in-memory job dict and streams JSON events
- **Upload sessions** — batch filenames stored server-side in `upload_sessions` dict (keyed by UUID) to avoid Gunicorn's 4094-char URL limit

### Image processing

- ImageMagick 7.1.2-18 (built from source on amd64, installed via apt on arm64)
- JXL support via `libjxl-tools` (`cjxl` / `djxl`)
- RAW support via ExifTool (dimension extraction for ARW files)
- Vector output (SVG, EPS, PDF, AI) requires `potrace` — checked at runtime before building the ImageMagick command
- All subprocess calls use list form, never `shell=True`

### Frontend

- All templates extend `base.html` via Jinja2 `{% extends %}`
- Design system: dark theme, violet accent (`#8b5cf6`), DM Sans + DM Mono (Google Fonts)
- CSS variables defined in `base.html` `:root` — do not redefine in child templates
- No JS frameworks — vanilla JS only
- XHR upload with progress bar in `index.html`; batch progress via EventSource (SSE)

---

## Security constraints

These are non-negotiable — do not remove or weaken them:

- `secure_filename(os.path.basename(filename))` applied at the **top of every route** that takes a filename from the URL or form
- `secure_path()` used on every file path before filesystem access — confines to `uploads/` and `output/`
- `ALLOWED_OUTPUT_FORMATS` — explicit set; any format value not in it is rejected to `''`
- `ALLOWED_SHARPEN_LEVELS` — `{'low', 'standard', 'high'}`; unknown values fall back to `'standard'`
- `POTRACE_FORMATS` — vector formats checked for `potrace` availability before building the command
- `is_safe_url()` — full DNS resolution + rejection of private/loopback/link-local/multicast IPs (SSRF prevention)
- All subprocess calls use list arguments — never build shell strings with user data

---

## GitHub Actions

Workflows live in `.github/workflows/`. Key conventions:

- Secrets: `DOCKER_USERNAME` and `DOCKER_PASSWORD` (not `DOCKERHUB_*`)
- Actions are SHA-pinned where possible, with version comment (e.g. `# v4.2.2`)
- Each job has `permissions: contents: read`; a global `permissions: contents: read` block sits above `jobs:`
- Standard action versions in use:
  - `actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683` # v4.2.2
  - `docker/login-action@74a5d142397b4f367a81961eba4e8cd7edddf772` # v3.4.0
  - `docker/setup-qemu-action@v3` (SHA pin pending)
  - `docker/setup-buildx-action@v3` (SHA pin pending)
  - `docker/build-push-action@v6` (SHA pin pending)
  - `peter-evans/dockerhub-description@v5` (SHA pin pending)

---

## Docker Hub

- Account: `tiritibambix`
- Image: `tiritibambix/imaguick`
- Tags: `latest` (main branch), `test` (test branch), short Git SHA

---

## Known constraints and gotchas

- **potrace must be installed** for SVG/EPS/PDF/AI output. The Dockerfile installs it via `apt-get install potrace`. Without it, ImageMagick raises a delegate error.
- **ARM64 uses apt ImageMagick**, not the source-compiled version — may be an older build. JXL support may be limited on arm64.
- **In-memory job state** is lost on container restart — any in-flight batch jobs are abandoned. This is acceptable for the current use case (local/trusted network).
- **`upload_sessions` dict grows indefinitely** — sessions are never explicitly purged. Not a problem at typical self-hosted scale.
- **`cleanup.py`** removes files from `uploads/` and `output/` older than 48 h. Batch output subdirectories (e.g. `output/batch_20240101_120000/`) are also cleaned.
- **Gunicorn 4094-char URL limit** — batch filenames must go through the server-side `upload_sessions` mechanism, not the query string.
- The `flask_error` / `flash_error` function logs and renders `result.html` with `success=False`. Use it consistently for error returns instead of ad-hoc `render_template` calls.

---

## Development notes

- Python 3.9+ required (f-strings, `subprocess` keyword args)
- No test suite currently exists
- Commit messages in English
- Commit titles follow conventional commits format: `type(scope): description`
- When modifying templates: always extend `base.html`, never duplicate `:root` or `body` styles
- When modifying `app.py`: run through the security checklist above before committing