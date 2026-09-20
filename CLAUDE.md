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
Dockerfile              # Multi-arch Docker build (ImageMagick compiled from source on both arches)
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

- **Flask + Gunicorn** (gthread worker, **exactly 1 worker process** × 16 threads — see `start.sh` comment: `jobs`/`upload_sessions`/the ImageMagick semaphore are plain in-process Python state with no external store, so they are only consistent within a single worker process; more than one worker causes spurious "No files selected"/"Job not found" errors when a request lands on a worker that never saw an earlier request's state)
- **No database** — job state held in-memory in the `jobs` dict (protected by `jobs_lock`), purged after `JOBS_TTL_HOURS` via `purge_old_jobs()`
- **Async batch processing** via `ThreadPoolExecutor` (16 workers) + `BoundedSemaphore(4)` for ImageMagick concurrency
- **SSE streaming** — `/job/<id>/status` polls the in-memory job dict and streams JSON events; the payload's `kind` field (`'batch'` or `'gif_create'`) and `output`/`zip` fields tell `progress.html` which single-file vs. ZIP download link to show
- **Upload sessions** — batch/GIF-creation filenames stored server-side in `upload_sessions` dict (keyed by UUID) to avoid the URL length limit set by Gunicorn's `--limit-request-line 8190` (see `start.sh`)
- **GIF/WEBP creation** (`process_gif_create_job()`) runs in two stages, which is what makes its progress measurable: `prepare_gif_frame()` normalises each frame in its own ImageMagick process (orientation + canvas), submitted to the shared executor under the same semaphore batch resize uses, then `build_gif_assemble_command()` assembles the already-normalised frames in one final pass. Frames land in `output/gifframes_<job_id>/`, removed in a `finally` regardless of outcome. Beyond progress, this keeps peak memory to one frame instead of the whole coalesced sequence, and leaves the assembly working on already-resized images
- **The GIF progress bar is a count, never an estimate.** The frame stage owns `GIF_FRAME_PHASE_PERCENT` of the bar and its value is `round(80 * frames_done / total)` — finished subprocesses, counted in Python, with nothing parsed. The assembly that follows is one indivisible invocation, so the bar goes **indeterminate** (`indeterminate` on the job and in the SSE payload) rather than inventing a figure. An earlier version assigned each ImageMagick operation a hand-picked slice of the bar; that is what produced a meaningless "14 of 14" frozen at the end of reading, and stage names scrolling past while the bar sat still. Do not reintroduce weighted bands.
  - `run_with_progress()` still runs the assembly under `-monitor` via `Popen`, but only to name the current operation (`make_gif_assembly_reporter()` → `phase_detail`) and to refresh liveness. Tags are mapped through `_MONITOR_STAGE_NAMES`, which matches what ImageMagick actually emits — `-colors` reports as `Classify/Image` then `Assign/Image` (see `MagickCore/quantize.c`), never "quantize" — and an unrecognised tag falls back to its own operation name instead of being dropped.
  - **Some steps report nothing at all.** `OptimizeLayerFrames()`, which is what `-layers optimize` runs, has no progress monitor, so silence there is expected. The job carries `stage_started_at` / `last_event_at`, streamed as `stage_seconds` / `idle_seconds`; the page shows a per-stage timer plus a note past `MONITOR_IDLE_HINT_SECONDS`. That timer is what distinguishes working from hung.
  - `run_with_progress()` raises exactly what `subprocess.run(check=True)` would, keeping timeout and error handling unchanged, and strips progress lines out of the stderr used for user-facing messages
- **GIF/WEBP editing** (`/gif_edit/<filename>`) is synchronous, mirroring `/resize/<filename>`'s pattern, since edits operate on one already-uploaded file and are bounded

### Image processing

- ImageMagick 7.1.2-31, built from source on **both** architectures. The version lives in a single `ARG IMAGEMAGICK_VERSION` in the Dockerfile and is asserted at build time (`magick -version | grep -q`), so a wrong tarball fails the build instead of shipping
- JXL support via `libjxl-tools` (`cjxl` / `djxl`)
- RAW support via ExifTool (dimension extraction) + dcraw (decode to TIFF via `prepare_input_file()`)
- WebP support via `libwebp-dev` + `pkg-config` (needed for *animated* WEBP muxing, not just single-frame WEBP — ImageMagick's `./configure` detects delegate libraries like libwebp via pkg-config, so both packages are required on the amd64 source-build path) — `webp_animation_supported()` reads the WEBP row of `magick -list format` once at startup (logged) and is re-checked before any GIF/WEBP route accepts `WEBP` as an output format
- Vector output (SVG, EPS, PDF, AI) requires `potrace` — checked at runtime before building the ImageMagick command
- **GIF/WEBP animation** — creation is split across `build_gif_frame_command()` (one frame: `-auto-orient`, plus `-resize`/`-extent` when a canvas was requested) and `build_gif_assemble_command()` (`-delay`/`-loop` over the normalised frames, then palette and optimisation). There is deliberately no `-coalesce` on the creation path: these are still images with no frame-disposal history, and coalescing them forces a full RGBA materialisation of the sequence. `build_gif_edit_command()` handles resize/optimize/speed/reverse/rotate/loop on an existing animated file; `build_gif_extract_command()` pulls one frame, a range, or all frames via ImageMagick's `file[N]`/`file[N-M]` subimage syntax. RAW/JXL files are not supported as GIF-creation frames (they'd need the same dcraw/djxl pre-decode `prepare_input_file()` does for the resize pipeline, which the GIF path doesn't call) — rejected explicitly rather than failing silently.
- All subprocess calls use list form, never `shell=True`
- **Argument order in `build_imagemagick_command()` is load-bearing**: `-density` and `-define jpeg:size=` are *read-time* settings and must precede the input path; `-auto-orient` must precede `-strip`, which would otherwise discard the EXIF orientation before it is applied; cropping precedes `-resize` so the resize geometry frames the cropped image. `jpeg:size` makes libjpeg decode at a reduced scale, so it is emitted **only** for absolute bounding-box geometries — never alongside a percentage resize or a pixel crop box, both of which are measured against the decoded image and would silently operate on the wrong size (`jpeg_decode_hint()` encodes this rule)
- **Reading `magick -list format`** — the columns are Format / Module / Mode / Description. Locate the mode by its shape via `parse_format_row()`, never by index: reading position 1 returns *Module*. `webp_animation_supported()` relies on the `+` in the WEBP row's mode, which is what marks multi-image support; it does not use `-list delegate`, which reports external delegate programs rather than built-in coders like libwebp

### Frontend

- All templates extend `base.html` via Jinja2 `{% extends %}`; `resize.html`/`resize_batch.html`/`gif_create.html`/`gif_edit.html` also share `_resize_options_styles.html` (CSS) and `_resize_form_fields.html` (Jinja macros) to avoid re-duplicating the options-page layout
- Design system: dark theme, violet accent (`#8b5cf6`), DM Sans + DM Mono (Google Fonts)
- CSS variables defined in `base.html` `:root` — do not redefine in child templates
- Sticky header/nav (`base.html`) with an inline SVG `<symbol>` icon sprite — add new icons there, reference via `<svg class="icon"><use href="#icon-name"></use></svg>`
- No JS frameworks, no build step — vanilla JS only
- XHR upload with progress bar in `index.html`; batch/GIF-creation progress via EventSource (SSE) in `progress.html`
- **GIF creation preview** (`gif_create.html`) preloads every frame as a decoded `Image` and then plays them on a `<canvas>` from a `requestAnimationFrame` accumulator. Both halves matter: frames are fetched from `/preview_frame/<filename>?w=<px>` as PIL-generated thumbnails (`build_preview_thumbnail()`, JPEG draft mode + an in-memory cache bounded by `PREVIEW_CACHE_MAX_ENTRIES`) rather than full-resolution originals, and playback is driven by elapsed time rather than `setInterval` + `<img src>` swapping, which used to make frame duration depend on network and decode latency. Thumbnail width scales down as frame count grows, since every frame stays decoded in memory for the session
- `index.html` has a Resize / Create GIF·WEBP tab switcher; the GIF tab enables drag-to-reorder on the selected-files list (order becomes frame order) and sets a hidden `intent` field read by `/upload`
- **The GIF tab covers both creation and editing**, decided by what was uploaded: several images go to `gif_create_options`, a single animated file (`is_animated_file()`, extension-gated on `ANIMATED_EXTENSIONS` then confirmed with PIL) goes to `gif_edit_options`. Before this, the editor was only reachable from an inline link on the resize options page, so users looking for it on the GIF tab hit "at least 2 images" and never found it. That resize-page link is kept as a second way in.

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
- **Never pin the base image to `$BUILDPLATFORM`**, and never pass `TARGETARCH` as an explicit `build-args` from CI. Both mistakes shipped together: the workflows passed `TARGETARCH=${{ matrix.arch }}` while defining no matrix, so the value was empty and the Dockerfile's arm64 branch never ran, while `FROM --platform=$BUILDPLATFORM` baked the runner's architecture into every image — meaning the published arm64 manifest entry carried amd64 binaries. Both architectures now build ImageMagick from source; Debian's `imagemagick` package is ImageMagick 6 and ships no `magick` binary, so an apt path was never viable for this app anyway.
- **Animated WEBP support depends on `libwebpmux`/`libwebpdemux` being linked into ImageMagick at build time** — the Dockerfile installs `libwebp-dev` for this, but it's a build-time detection (via `./configure`), not guaranteed. Always check via `webp_animation_supported()` / `docker logs` rather than assuming; the UI hides/disables the WEBP option server-side when unsupported.
- **Gunicorn MUST run with exactly one worker process** (`--workers 1` in `start.sh`) — `jobs`, `upload_sessions`, `_processing_semaphore`, `executor`, and `_webp_anim_supported_cache` are all plain in-process Python objects with no shared/external store. Multiple worker processes each get their own independent copy, so a request that lands on a different worker than an earlier one in the same flow (upload → options page → submit) won't see that earlier worker's state — this previously caused real, reproducible "No files selected" (upload_sessions) and would equally cause "Job not found" (jobs) failures under the `--workers 4` config that shipped before this was diagnosed. Scale via `--threads` (in-process, shares memory) instead of `--workers`.
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