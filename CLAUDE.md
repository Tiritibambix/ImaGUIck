# CLAUDE.md

This file provides context for Claude when working on this codebase.

---

## Project overview

ImaGUIck is a self-hosted Flask web application for single/batch image resizing, format conversion, and GIF/WEBP animation creation & editing, powered by ImageMagick. It is deployed via Docker (multi-arch: amd64 + arm64) and published on Docker Hub as `tiritibambix/imaguick`.

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
  base.html                    # Design system: CSS variables, shared header/nav, SVG icon sprite, DM Sans + DM Mono fonts
  index.html                   # Upload page — Resize / Create GIF·WEBP tabs, drag-and-drop, XHR upload, URL import
  resize.html                  # Single-image resize options
  resize_batch.html            # Batch resize options
  gif_create.html               # Create an animated GIF/WEBP from a sequence of uploaded images
  gif_edit.html                 # Edit an existing animated GIF/WEBP (resize/optimize/speed/reverse/rotate/loop/extract)
  progress.html                 # Real-time SSE progress page for batch jobs and GIF creation
  result.html                   # Success / error result page
  _resize_options_styles.html   # Shared <style> partial for the resize/GIF options-page layout
  _resize_form_fields.html      # Shared Jinja macros for repeated form field groups
static/media/           # Logo, banner, favicon
.github/workflows/
  docker-build.yml      # CI/CD: build + push multi-arch image to Docker Hub (main branch)
  docker-build-test.yml # CI/CD: build + push test image (test branch)
```

---

## Architecture decisions

### Backend

- **Flask + Gunicorn** (gthread worker, 4 workers × 8 threads)
- **No database** — job state held in-memory in the `jobs` dict (protected by `jobs_lock`), purged after `JOBS_TTL_HOURS` via `purge_old_jobs()`
- **Async batch processing** via `ThreadPoolExecutor` (16 workers) + `BoundedSemaphore(4)` for ImageMagick concurrency
- **SSE streaming** — `/job/<id>/status` polls the in-memory job dict and streams JSON events; the payload's `kind` field (`'batch'` or `'gif_create'`) and `output`/`zip` fields tell `progress.html` which single-file vs. ZIP download link to show
- **Upload sessions** — batch/GIF-creation filenames stored server-side in `upload_sessions` dict (keyed by UUID) to avoid the URL length limit set by Gunicorn's `--limit-request-line 8190` (see `start.sh`)
- **GIF/WEBP creation** (`process_gif_create_job()`) reuses the same `jobs`/executor/semaphore apparatus as batch resize, as a single unit of work (one ImageMagick invocation over N ordered frames) rather than N independent ones
- **GIF/WEBP editing** (`/gif_edit/<filename>`) is synchronous, mirroring `/resize/<filename>`'s pattern, since edits operate on one already-uploaded file and are bounded

### Image processing

- ImageMagick 7.1.2-18 (built from source on amd64, installed via apt on arm64)
- JXL support via `libjxl-tools` (`cjxl` / `djxl`)
- RAW support via ExifTool (dimension extraction) + dcraw (decode to TIFF via `prepare_input_file()`)
- WebP support via `libwebp-dev` + `pkg-config` (needed for *animated* WEBP muxing, not just single-frame WEBP — ImageMagick's `./configure` detects delegate libraries like libwebp via pkg-config, so both packages are required on the amd64 source-build path) — `webp_animation_supported()` checks `magick -list delegate` once at startup (logged) and is re-checked before any GIF/WEBP route accepts `WEBP` as an output format
- Vector output (SVG, EPS, PDF, AI) requires `potrace` — checked at runtime before building the ImageMagick command
- **GIF/WEBP animation** — `build_gif_create_command()` assembles a frame sequence with `-delay`/`-loop`/`-coalesce`; `build_gif_edit_command()` handles resize/optimize/speed/reverse/rotate/loop on an existing animated file; `build_gif_extract_command()` pulls one frame, a range, or all frames via ImageMagick's `file[N]`/`file[N-M]` subimage syntax. RAW/JXL files are not supported as GIF-creation frames (they'd need the same dcraw/djxl pre-decode `prepare_input_file()` does for the resize pipeline, which the GIF path doesn't call) — rejected explicitly rather than failing silently.
- All subprocess calls use list form, never `shell=True`

### Frontend

- All templates extend `base.html` via Jinja2 `{% extends %}`; `resize.html`/`resize_batch.html`/`gif_create.html`/`gif_edit.html` also share `_resize_options_styles.html` (CSS) and `_resize_form_fields.html` (Jinja macros) to avoid re-duplicating the options-page layout
- Design system: dark theme, violet accent (`#8b5cf6`), DM Sans + DM Mono (Google Fonts)
- CSS variables defined in `base.html` `:root` — do not redefine in child templates
- Sticky header/nav (`base.html`) with an inline SVG `<symbol>` icon sprite — add new icons there, reference via `<svg class="icon"><use href="#icon-name"></use></svg>`
- No JS frameworks, no build step — vanilla JS only
- XHR upload with progress bar in `index.html`; batch/GIF-creation progress via EventSource (SSE) in `progress.html`
- `index.html` has a Resize / Create GIF·WEBP tab switcher; the GIF tab enables drag-to-reorder on the selected-files list (order becomes frame order) and sets a hidden `intent` field read by `/upload`

---

## Security constraints

These are non-negotiable — do not remove or weaken them:

- `secure_filename(os.path.basename(filename))` applied at the **top of every route** that takes a filename from the URL or form
- `secure_path()` used on every file path before filesystem access — confines to `uploads/` and `output/`
- `ALLOWED_OUTPUT_FORMATS` — explicit set; any format value not in it is rejected to `''`
- `ALLOWED_SHARPEN_LEVELS` — `{'low', 'standard', 'high'}`; unknown values fall back to `'standard'`
- `POTRACE_FORMATS` — vector formats checked for `potrace` availability before building the command
- `is_safe_url()` — full DNS resolution + rejection of private/loopback/link-local/multicast IPs (SSRF prevention)
- `MAX_DIMENSION` is enforced on **both** input (`get_image_dimensions()`) and output (`build_imagemagick_command()` rejects any requested width/height/percentage that would exceed it); `GIF_MAX_OUTPUT_DIMENSION`/`GIF_MAX_FRAMES`/`GIF_MAX_TOTAL_PIXELS` do the equivalent for GIF/WEBP creation and editing, checked before any decode/processing work
- `SUBPROCESS_TIMEOUT_SHORT/MEDIUM/LONG` — every `subprocess.run()` call has an explicit timeout
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
- **ARM64 uses apt ImageMagick**, not the source-compiled version — may be an older build. JXL support may be limited on arm64. Version is unpinned on arm64 (pinned to 7.1.2-18 on amd64).
- **Animated WEBP support depends on `libwebpmux`/`libwebpdemux` being linked into ImageMagick at build time** — the Dockerfile installs `libwebp-dev` for this, but it's a build-time detection (via `./configure`), not guaranteed. Always check via `webp_animation_supported()` / `docker logs` rather than assuming; the UI hides/disables the WEBP option server-side when unsupported.
- **In-memory job state** is lost on container restart — any in-flight batch jobs or GIF creation jobs are abandoned. This is acceptable for the current use case (local/trusted network).
- **`upload_sessions` dict grows indefinitely** — sessions are never explicitly purged. Not a problem at typical self-hosted scale. (Unlike `jobs`, which is purged — see `purge_old_jobs()` / `JOBS_TTL_HOURS`.)
- **`cleanup.py`** removes files from `uploads/` and `output/` older than 48 h. Batch output subdirectories (e.g. `output/batch_20240101_120000/`) and GIF frame-extraction temp directories are also cleaned (the latter are additionally removed immediately after zipping in `/gif_edit`, so `cleanup.py` is only a backstop for interrupted requests).
- **Gunicorn's `--limit-request-line 8190` URL limit** — batch and GIF-creation filenames must go through the server-side `upload_sessions` mechanism, not the query string.
- **GIF creation doesn't call `prepare_input_file()`** — RAW/JXL frames are explicitly rejected (`gif_create_options`/`gif_create`) rather than silently mishandled, since ImageMagick would receive the raw/undecoded file directly.
- The `flask_error` / `flash_error` function logs and renders `result.html` with `success=False`. Use it consistently for error returns instead of ad-hoc `render_template` calls.

---

## Development notes

- Python 3.9+ required (f-strings, `subprocess` keyword args)
- No test suite currently exists
- Commit messages in English
- Commit titles follow conventional commits format: `type(scope): description`
- When modifying templates: always extend `base.html`, never duplicate `:root` or `body` styles
- When modifying `app.py`: run through the security checklist above before committing