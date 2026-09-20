from flask import Flask, render_template, request, redirect, url_for, send_file, flash, Response
import io
import os
import subprocess
import uuid
import threading
import json
import time
import atexit
import shutil
from zipfile import ZipFile
from datetime import datetime
from PIL import Image, ImageOps
import requests
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import socket
import ipaddress
from urllib.parse import urlparse, urlunparse

# Configuration
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'output'
MAX_DIMENSION = 10000
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024   # 2 GB — total request limit (MAX_CONTENT_LENGTH)
PER_FILE_MAX_SIZE = 200 * 1024 * 1024    # 200 MB — per individual file
JOBS_TTL_HOURS = 2                       # completed batch jobs are purged from memory after this long
DEFAULTS = {
    "quality": "100",
    "width": "",
    "height": "",
    "percentage": "",
}

# Subprocess timeouts, in seconds
SUBPROCESS_TIMEOUT_SHORT = 30    # format probing, delegate checks, dimension lookups
SUBPROCESS_TIMEOUT_MEDIUM = 120  # single-image processing
SUBPROCESS_TIMEOUT_LONG = 300    # batch per-file / GIF creation processing

# GIF/WEBP animation creation & editing limits — checked before any decode/
# processing work, to keep memory and CPU use bounded regardless of user input.
GIF_MAX_FRAMES = 500
GIF_MAX_OUTPUT_DIMENSION = 4000        # stricter than MAX_DIMENSION: many frames at 10000px would be excessive
GIF_MAX_TOTAL_PIXELS = 500_000_000     # sum of width*height across all frames (~2GB of raw RGBA when coalesced)
GIF_CREATE_OUTPUT_FORMATS = {'GIF', 'WEBP'}
GIF_EXTRACT_FORMATS = {'PNG', 'WEBP'}
GIF_EDIT_MODES = {'resize', 'optimize', 'speed', 'reverse', 'rotate', 'extract', 'loop'}
ANIMATED_EXTENSIONS = {'.gif', '.webp'}

# GIF-creation preview: frames are served to the browser downscaled, so playback
# stays smooth even when the uploaded frames are full-resolution photos.
PREVIEW_MAX_WIDTH = 960
PREVIEW_CACHE_MAX_ENTRIES = 64

# Allowlist of accepted output formats — prevents path injection via format field
ALLOWED_OUTPUT_FORMATS = {
    'PNG', 'JPEG', 'JPG', 'WEBP', 'AVIF', 'GIF', 'TIFF', 'BMP', 'ICO',
    'HEIC', 'JXL', 'SVG', 'PDF', 'EPS', 'PSD', 'DNG', 'APNG', 'MNG',
    'TGA', 'PCX', 'PPM', 'PGM', 'PNM', 'HDR', 'EXR', 'DPX', 'MIFF',
    'XBM', 'XPM', 'PICON', 'CUR', 'ICON', 'ARW', 'CR2', 'CR3', 'NEF',
    'RAF', 'RW2', 'AI', 'EMF', 'WMF', 'PSB', 'XCF',
}

ALLOWED_SHARPEN_LEVELS = {'low', 'standard', 'high'}

# Output formats with no alpha channel: converting a transparent source to one
# of these without flattening first renders the transparent areas black.
OPAQUE_OUTPUT_FORMATS = {'JPEG', 'JPG', 'BMP', 'PCX', 'PPM', 'PGM'}
ALLOWED_BACKGROUND_COLORS = {'white', 'black', 'gray'}
HEX_COLOR_RE = re.compile(r'^#[0-9a-fA-F]{6}$')

# Vector sources are rasterized at 72 dpi unless told otherwise, which is why
# an imported SVG/PDF looks soft. Density is a read-time setting.
VECTOR_INPUT_EXTENSIONS = {'.svg', '.pdf', '.eps', '.ai'}
ALLOWED_DENSITIES = {'72', '150', '300', '600'}

# Aspect ratios offered for centred cropping, as (width, height) multipliers.
ALLOWED_CROP_RATIOS = {'1:1': (1, 1), '4:3': (4, 3), '3:2': (3, 2), '16:9': (16, 9)}

# Formats that require potrace (raster-to-vector delegate)
POTRACE_FORMATS = {'SVG', 'EPS', 'AI', 'PDF', 'WMF', 'EMF'}

# Single source of truth for accepted image extensions. Used both for direct
# upload (UPLOAD_EXTENSIONS below) and, extended with a few document-ish
# vector formats, for URL import (URL_IMPORT_EXTENSIONS in is_safe_url).
IMAGE_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.tiff', '.bmp', '.arw',
    '.jxl', '.dng', '.cr2', '.cr3', '.nef', '.raf', '.rw2', '.heic',
    '.avif', '.apng',
}

# Extensions accepted for URL import (is_safe_url) — a superset of IMAGE_EXTENSIONS
# that also allows a few vector/document formats not offered for direct upload.
URL_IMPORT_EXTENSIONS = IMAGE_EXTENSIONS | {'.svg', '.pdf', '.eps'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE
app.config['UPLOAD_EXTENSIONS'] = sorted(IMAGE_EXTENSIONS)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev-insecure-key-change-in-prod')
app.logger.setLevel(logging.INFO)

# --- Async batch processing state ---
jobs = {}
jobs_lock = threading.Lock()
_processing_semaphore = threading.BoundedSemaphore(4)
executor = ThreadPoolExecutor(max_workers=16)
atexit.register(lambda: executor.shutdown(wait=False, cancel_futures=True))

# Server-side upload sessions: maps a short key -> list of saved filenames.
# Avoids embedding long filename lists in redirect URLs (Gunicorn's
# --limit-request-line 8190, see start.sh).
upload_sessions = {}
upload_sessions_lock = threading.Lock()


@app.errorhandler(413)
def file_too_large(e):
    msg = 'Request too large. Reduce the number or size of your images.'
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return {'error': msg}, 413
    flash(msg, 'error')
    return redirect(url_for('index'))


def allowed_file(filename):
    """Allow all image file types supported by ImageMagick, but block potentially dangerous extensions.
    The allowlist below already restricts uploads to IMAGE_EXTENSIONS, so BLOCKED_EXTENSIONS can never
    actually reject anything today — it's kept as intentional defense-in-depth against a future accidental
    widening of UPLOAD_EXTENSIONS to include an executable-ish extension."""
    BLOCKED_EXTENSIONS = {'php', 'php3', 'php4', 'php5', 'phtml', 'exe', 'js', 'jsp', 'html', 'htm', 'sh', 'bash', 'py', 'pl'}
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    return ext and ext not in BLOCKED_EXTENSIONS and f'.{ext}' in app.config['UPLOAD_EXTENSIONS']


def secure_path(filepath):
    """Ensure the filepath is secure and within allowed directories."""
    try:
        abs_path = os.path.abspath(filepath)
        base_path = os.path.abspath(os.path.join(app.config['UPLOAD_FOLDER'], ''))
        output_path = os.path.abspath(os.path.join(app.config['OUTPUT_FOLDER'], ''))

        if not (abs_path.startswith(base_path) or abs_path.startswith(output_path)):
            return None

        real_path = os.path.realpath(abs_path)
        if not (real_path.startswith(base_path) or real_path.startswith(output_path)):
            return None

        return abs_path
    except Exception:
        return None


def is_valid_tmp_path(filepath):
    """Check if a path is a valid imaguick-generated temp file in /tmp."""
    basename = os.path.basename(filepath)
    return (
        filepath.startswith('/tmp/imaguick_') and
        re.match(r'^imaguick_[a-f0-9]{32}\.(png|tiff)$', basename) is not None
    )


_WINDOWS_RESERVED_NAMES = {
    'CON', 'PRN', 'AUX', 'NUL',
    *(f'COM{i}' for i in range(1, 10)),
    *(f'LPT{i}' for i in range(1, 10)),
}


def safe_display_filename(filename, fallback='file'):
    """Sanitize a filename for storage/display while preserving spaces, accents,
    and punctuation that Werkzeug's secure_filename() strips. secure_path() is
    the actual defense against directory traversal (confines the resolved
    absolute path to uploads/output); this only removes what's genuinely unsafe
    as a filesystem path component or in a Content-Disposition header.
    Idempotent: re-applying it to its own output is a no-op — required since
    it's reused both to sanitize a brand-new upload AND to re-validate a
    filename that arrived as a URL path parameter and must still match the
    exact file already on disk."""
    name = os.path.basename(filename or '').strip()
    name = re.sub(r'[\x00-\x1f\x7f<>:"|?*\\/]', '', name)
    name = re.sub(r'\s+', ' ', name).strip(' .')
    if not name:
        return fallback
    base, ext = os.path.splitext(name)
    if base.upper() in _WINDOWS_RESERVED_NAMES:
        base = f'_{base}'
    name = f'{base}{ext}'
    if len(name) > 200:
        base, ext = os.path.splitext(name)
        name = base[:200 - len(ext)] + ext
    return name or fallback


def is_unsafe_filename(name):
    """True if name could indicate a path-traversal attempt or an unsafe
    filesystem name. secure_path() is the real traversal defense (resolved
    absolute path confinement); this is a fast pre-check that — unlike the
    old `^[\\w\\-.]+$` allowlist regex it replaces — doesn't reject legitimate
    filenames containing spaces, `&`, or accented characters."""
    return (not name or '/' in name or '\\' in name or '..' in name
            or name.startswith('.') or '\x00' in name)


# RAW formats that require dcraw pre-processing before ImageMagick
RAW_FORMATS_DCRAW = {'.arw', '.dng', '.cr2', '.cr3', '.nef', '.raf', '.rw2'}

def prepare_input_file(filepath):
    """Decode special formats to a temp file before passing to ImageMagick.
    - JXL: decoded to PNG via djxl
    - RAW (ARW, DNG, CR2, CR3, NEF, RAF, RW2): decoded to TIFF via dcraw
    Returns (input_path, tmp_path). tmp_path is None if no temp was created.
    Caller is responsible for deleting tmp_path (use try/finally)."""
    ext = os.path.splitext(filepath)[1].lower()

    if ext == '.jxl':
        validated = secure_path(filepath)
        if not validated:
            raise ValueError(f"Insecure JXL path: {filepath}")
        tmp_path = f'/tmp/imaguick_{uuid.uuid4().hex}.png'
        subprocess.run(['djxl', '--', validated, tmp_path], check=True, timeout=60)
        return tmp_path, tmp_path

    if ext in RAW_FORMATS_DCRAW:
        validated = secure_path(filepath)
        if not validated:
            raise ValueError(f"Insecure RAW path: {filepath}")
        tmp_path = f'/tmp/imaguick_{uuid.uuid4().hex}.tiff'
        # -T: output TIFF, -w: camera white balance, -6: 16-bit, -c: write to stdout
        # Pipe stdout to the temp file — dcraw does not support -O or -- separator
        with open(tmp_path, 'wb') as out_f:
            subprocess.run(
                ['dcraw', '-T', '-w', '-6', '-c', validated],
                stdout=out_f, check=True, timeout=120
            )
        return tmp_path, tmp_path

    return filepath, None


def get_image_dimensions(filepath):
    """Get image dimensions using appropriate tool based on file type."""
    try:
        secure_file_path = secure_path(filepath)
        if not secure_file_path:
            raise Exception("Invalid file path")

        RAW_EXTENSIONS = {'.arw', '.dng', '.cr2', '.cr3', '.nef', '.raf', '.rw2'}
        if any(filepath.lower().endswith(ext) for ext in RAW_EXTENSIONS):
            app.logger.info(f"Getting dimensions for RAW file: {filepath}")
            # Use ImageWidth/ImageHeight for full-resolution RAW dimensions
            cmd = ['exiftool', '-s', '-s', '-s', '-ImageWidth', '-ImageHeight', secure_file_path]
            app.logger.info(f"Running exiftool command")
            result = subprocess.run(cmd, capture_output=True, text=True, shell=False, timeout=SUBPROCESS_TIMEOUT_SHORT)

            if result.returncode == 0 and result.stdout.strip():
                app.logger.info(f"Exiftool output received")
                dimensions = result.stdout.strip().split('\n')
                if len(dimensions) == 2:
                    try:
                        width = int(dimensions[0])
                        height = int(dimensions[1])
                        if not (0 < width <= MAX_DIMENSION and 0 < height <= MAX_DIMENSION):
                            raise ValueError(f"Image dimensions ({width}x{height}) exceed maximum allowed ({MAX_DIMENSION}px)")
                        app.logger.info(f"Successfully parsed dimensions: {width}x{height}")
                        return width, height
                    except ValueError:
                        app.logger.warning("Could not parse dimensions from exiftool output")
                        pass

            return None, None
        else:
            app.logger.info(f"Getting dimensions for non-ARW file")
            # -ping reads the header only instead of decoding the whole image,
            # and -format asks for exactly the two numbers we want, which
            # replaces scraping them out of identify's free-form line. [0]
            # selects the first frame so an animation yields a single row.
            cmd = ['magick', 'identify', '-ping', '-format', '%w %h', f'{secure_file_path}[0]']
            app.logger.info(f"Running ImageMagick command")
            result = subprocess.run(cmd, capture_output=True, text=True, shell=False, timeout=SUBPROCESS_TIMEOUT_SHORT)
            if result.returncode != 0:
                raise Exception(f"Error getting image dimensions: {result.stderr}")

            match = re.match(r'^\s*(\d+)\s+(\d+)\s*$', result.stdout)
            if match:
                width = int(match.group(1))
                height = int(match.group(2))
                if not (0 < width <= MAX_DIMENSION and 0 < height <= MAX_DIMENSION):
                    raise ValueError(f"Image dimensions ({width}x{height}) exceed maximum allowed ({MAX_DIMENSION}px)")
                app.logger.info(f"Successfully parsed dimensions: {width}x{height}")
                return width, height
            else:
                raise Exception("Could not parse image dimensions")
    except Exception as e:
        app.logger.error(f"Error getting image dimensions: {str(e)}")
        return None, None


def get_format_categories():
    """Categorize image formats by their typical usage."""
    return {
        'photo': {
            'name': 'Photography & Print',
            'formats': [
                'JPEG', 'JPG', 'TIFF', 'ARW', 'CR2', 'CR3', 'NEF', 'RAF',
                'DNG', 'HEIC', 'BMP', 'PPM', 'PGM', 'PNM'
            ]
        },
        'web': {
            'name': 'Web & Mobile',
            'formats': ['WEBP', 'AVIF', 'JPEG', 'JPG', 'PNG', 'GIF', 'JXL']
        },
        'graphics': {
            'name': 'Graphics & Design',
            'formats': [
                'PNG', 'SVG', 'AI', 'EPS', 'PS', 'PDF', 'EMF', 'WMF',
                'PCX', 'TGA'
            ]
        },
        'icons': {
            'name': 'Icons & UI',
            'formats': ['ICO', 'CUR', 'ICON', 'PICON', 'XBM', 'XPM']
        },
        'animation': {
            'name': 'Animation',
            'formats': ['GIF', 'APNG', 'MNG', 'WEBP']
        },
        'archive': {
            'name': 'Archive & Storage',
            'formats': [
                'PSD', 'XCF', 'PDF', 'PSB', 'TIFF', 'DPX', 'EXR',
                'HDR', 'MIFF'
            ]
        }
    }


def get_recommended_formats_for_image(image_type, original_format):
    """Get recommended formats based on image characteristics."""
    recommended = set()

    # PNG is always recommended as an excellent lossless format
    recommended.add('PNG')

    if image_type.get('has_transparency'):
        recommended.update(['WEBP', 'AVIF'])

    if image_type.get('is_photo'):
        recommended.update(['JPEG', 'WEBP', 'AVIF', 'HEIC', 'JXL'])
    else:
        # For graphics, logos, etc.
        recommended.update(['WEBP', 'SVG', 'JXL'])

    # Special cases based on the original format
    if original_format:
        original_format = original_format.upper()
        if original_format in ['ARW', 'CR2', 'CR3', 'NEF', 'RAF', 'RW2', 'DNG']:
            # TIFF 16-bit is the recommended output for RAW files — ImageMagick
            # cannot produce a proper compressed DNG, so DNG output is intentionally
            # excluded from recommendations. JPEG and WEBP are offered for delivery use.
            recommended.update(['TIFF', 'JPEG', 'WEBP', 'JXL'])
            recommended.discard('DNG')
        elif original_format in ['GIF', 'WEBP', 'MNG', 'APNG']:
            recommended.update(['GIF', 'WEBP', 'APNG'])
        elif original_format in ['ICO', 'CUR', 'ICON']:
            recommended.add('ICO')
        elif original_format in ['SVG', 'EPS', 'AI', 'PDF']:
            recommended.update(['SVG', 'PDF', 'EPS'])
        elif original_format in ['PSD', 'XCF', 'PSB']:
            recommended.update(['PSD', 'TIFF'])
        elif original_format in ['TIFF']:
            recommended.add('TIFF')

    return sorted(list(recommended))


# A `magick -list format` row is "<Format> <Module> <Mode> <Description>". The
# mode is located by its shape rather than by column index: reading it
# positionally means reading Module instead, which is how the format list used
# to drop PNG and JPEG while keeping WEBP (whose module name happens to contain
# a "w"). Mode is read / write / multi-image, e.g. "rw+", and is sometimes
# printed with only two characters.
_FORMAT_MODE_RE = re.compile(r'^[r-][w-][+-]?$')


def parse_format_row(line):
    """Pull (FORMAT, mode) out of one `magick -list format` row, or None if the
    line is a header, a rule, or otherwise not a format row."""
    parts = line.split()
    if len(parts) < 2:
        return None
    for token in parts[1:]:
        if _FORMAT_MODE_RE.match(token):
            return parts[0].strip('*').upper(), token.lower()
    return None


def get_available_formats(filepath=None):
    """Get all formats supported by ImageMagick and organize them by category."""
    try:
        VIDEO_FORMATS = {'3G2', '3GP', 'AVI', 'FLV', 'M4V', 'MKV', 'MOV', 'MP4', 'MPG', 'MPEG', 'OGV', 'SWF', 'VOB', 'WMV'}

        result = subprocess.run(['magick', '-list', 'format'], capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_SHORT)

        if result.returncode != 0:
            raise Exception("Failed to retrieve format list from ImageMagick")

        available_formats = set()
        for line in result.stdout.split('\n'):
            row = parse_format_row(line)
            if not row:
                continue
            format_name, format_mode = row
            if ('r' in format_mode or 'w' in format_mode) and format_name not in VIDEO_FORMATS:
                available_formats.add(format_name)

        if not available_formats:
            raise Exception("No formats found in ImageMagick output")

        app.logger.info(f"Detected formats: {available_formats}")

        categories = get_format_categories()
        categorized_formats = {}

        all_categorized = set()
        for cat_info in categories.values():
            all_categorized.update(cat_info['formats'])

        ordered_categories = ['recommended', 'photo', 'web', 'icons', 'animation', 'graphics', 'archive', 'other']

        if filepath and os.path.exists(filepath):
            image_type = analyze_image_type(filepath)
            if image_type:
                original_format = os.path.splitext(filepath)[1][1:].upper()
                recommended = get_recommended_formats_for_image(image_type, original_format)
                if recommended:
                    categorized_formats['recommended'] = {
                        'name': 'Recommended Formats',
                        'formats': [fmt for fmt in recommended if fmt in available_formats]
                    }

        for cat_key in ordered_categories:
            if cat_key == 'recommended' and 'recommended' in categorized_formats:
                continue
            elif cat_key == 'other':
                uncategorized = sorted(list(available_formats - all_categorized))
                if uncategorized:
                    categorized_formats['other'] = {
                        'name': 'Other Available Formats',
                        'formats': uncategorized
                    }
            elif cat_key in categories:
                matching_formats = sorted(list(available_formats.intersection(categories[cat_key]['formats'])))
                if matching_formats:
                    categorized_formats[cat_key] = {
                        'name': categories[cat_key]['name'],
                        'formats': matching_formats
                    }

        return categorized_formats

    except Exception as e:
        app.logger.error(f"Error retrieving format list: {e}")
        return {
            'other': {
                'name': 'Available Formats',
                'formats': sorted([
                    'PNG', 'JPEG', 'JPG', 'GIF', 'TIFF', 'BMP', 'WEBP',
                    'ICO', 'CUR', 'ICON', 'PICON',
                    'PDF', 'SVG', 'PSD',
                    'HEIC', 'AVIF'
                ])
            }
        }


_webp_anim_supported_cache = None


def webp_animation_supported():
    """Check (once, cached) whether this ImageMagick can write *animated* WEBP.
    Single-frame WEBP can work without it, so it must be checked separately
    before offering WEBP as a GIF-creation/editing output format.

    Read from the WEBP row of `magick -list format`, where the mode's `+` means
    the coder handles multiple images in one file — exactly what an animation
    needs. The previous check looked for the string "webp" anywhere in
    `-list delegate`, which reports *external* delegate programs; libwebp is
    linked in as a coder, so that test did not measure what it claimed to."""
    global _webp_anim_supported_cache
    if _webp_anim_supported_cache is not None:
        return _webp_anim_supported_cache
    try:
        result = subprocess.run(['magick', '-list', 'format'], capture_output=True,
                                 text=True, timeout=SUBPROCESS_TIMEOUT_SHORT)
        supported = False
        for line in result.stdout.split('\n'):
            row = parse_format_row(line)
            if row and row[0] == 'WEBP':
                supported = 'w' in row[1] and row[1].endswith('+')
                break
        _webp_anim_supported_cache = supported
    except Exception as e:
        app.logger.warning(f"Could not determine WebP animation support: {e}")
        _webp_anim_supported_cache = False
    return _webp_anim_supported_cache


app.logger.info(f"WebP animation (muxing) support: {'yes' if webp_animation_supported() else 'no'}")


def is_animated_file(filepath):
    """True if the file is a multi-frame GIF/WEBP, i.e. something the animation
    editor can work on. Gated on extension first so nothing else pays for a PIL
    open, and scoped to the formats that editor actually handles."""
    if os.path.splitext(filepath)[1].lower() not in ANIMATED_EXTENSIONS:
        return False
    try:
        with Image.open(filepath) as img:
            return bool(getattr(img, 'is_animated', False))
    except Exception as e:
        app.logger.info(f"Could not inspect {os.path.basename(filepath)} for animation: {e}")
        return False


def _analyze_with_pil(filepath):
    """Analyze image with PIL and return type dict."""
    with Image.open(filepath) as img:
        has_transparency = 'A' in img.getbands()
        is_photo = True
        if img.mode in ('P', '1', 'L'):
            is_photo = False
        elif img.mode in ('RGB', 'RGBA'):
            pixels = list(img.getdata())
            # Sample spread across the whole image, not just the top-left
            # corner, which is often a uniform sky/background region.
            step = max(1, len(pixels) // 1000)
            sample = pixels[::step][:1000]
            unique_colors = len(set(sample))
            is_photo = unique_colors > 100
        return {
            'has_transparency': has_transparency,
            'is_photo': is_photo,
            'original_format': img.format,
            'is_animated': getattr(img, 'is_animated', False),
            'n_frames': getattr(img, 'n_frames', 1),
        }


def analyze_image_type(filepath):
    """Analyze image to determine its type and best suitable formats."""
    try:
        validated_path = secure_path(filepath)
        if not validated_path or not os.path.exists(validated_path):
            raise ValueError("File does not exist or is not in an allowed directory.")

        if validated_path.lower().endswith('.arw'):
            app.logger.info(f"Analyzing RAW file: {validated_path}")
            return {'has_transparency': False, 'is_photo': True, 'original_format': 'ARW',
                    'is_animated': False, 'n_frames': 1}

        if validated_path.lower().endswith('.jxl'):
            tmp_path = f'/tmp/imaguick_{uuid.uuid4().hex}.png'
            try:
                subprocess.run(['djxl', '--', validated_path, tmp_path], check=True, timeout=60)
                return _analyze_with_pil(tmp_path)
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

        return _analyze_with_pil(validated_path)
    except Exception as e:
        app.logger.error(f"Error analyzing image: {e}")
        return {'has_transparency': False, 'is_photo': True, 'original_format': None,
                'is_animated': False, 'n_frames': 1}


def flash_error(message):
    """Flash error message and log if needed."""
    app.logger.error(message)
    flash(message)
    return render_template('result.html',
                           success=False,
                           title='Error',
                           return_url=request.referrer)


def resolve_missing_dimension(width, height, keep_ratio, filepath):
    """When keep_ratio is set and only one of width/height is provided, compute the
    other proportionally from the source image's own dimensions. Returns (width,
    height) unchanged otherwise. Shared by the single-image and batch resize paths
    so both apply the same non-upscaling, aspect-preserving behavior."""
    if not (keep_ratio and (width.isdigit() or height.isdigit())):
        return width, height
    original_dimensions = get_image_dimensions(filepath) if filepath else None
    if not (original_dimensions and original_dimensions[0] and original_dimensions[1]):
        return width, height
    original_width, original_height = original_dimensions
    if width.isdigit() and not height.isdigit():
        new_width = int(width)
        height = str(round(new_width * original_height / original_width))
    elif height.isdigit() and not width.isdigit():
        new_height = int(height)
        width = str(round(new_height * original_width / original_height))
    return width, height


def classify_processing_error(exc, stderr=''):
    """Map a processing exception to a safe, specific user-facing message.
    The raw exception/stderr is always logged separately — this only controls
    what the end user sees, so it must never leak paths or internal details."""
    if isinstance(exc, subprocess.TimeoutExpired):
        return 'Processing timed out. Try a smaller image, fewer frames, or lower quality.'
    text = (stderr or str(exc) or '').lower()
    if 'no decode delegate' in text or 'no encode delegate' in text or 'delegate failed' in text:
        return 'This format is not supported by the server (missing codec).'
    if 'cache resources exhausted' in text or 'memory' in text:
        return 'Image too large to process (memory limit exceeded).'
    return 'Processing error'


def extract_processing_params(form):
    """Extract all image processing parameters from a form."""
    raw_format = form.get('format', '').upper().strip()
    output_format = raw_format if raw_format in ALLOWED_OUTPUT_FORMATS else ''

    raw_sharpen = form.get('sharpen_level', 'standard').strip().lower()
    sharpen_level = raw_sharpen if raw_sharpen in ALLOWED_SHARPEN_LEVELS else 'standard'

    raw_background = form.get('background_color', 'white').strip().lower()
    if raw_background not in ALLOWED_BACKGROUND_COLORS and not HEX_COLOR_RE.match(raw_background):
        raw_background = 'white'

    raw_density = form.get('density', '').strip()
    density = raw_density if raw_density in ALLOWED_DENSITIES else ''

    raw_ratio = form.get('crop_ratio', '').strip()
    crop_ratio = raw_ratio if raw_ratio in ALLOWED_CROP_RATIOS else ''

    return {
        'width': form.get('width', DEFAULTS['width']),
        'height': form.get('height', DEFAULTS['height']),
        'percentage': form.get('percentage', DEFAULTS['percentage']),
        'quality': form.get('quality', DEFAULTS['quality']),
        'keep_ratio': 'keep_ratio' in form,
        'output_format': output_format,
        'auto_level': form.get('auto_level') == 'on',
        'auto_gamma': form.get('auto_gamma') == 'on',
        'use_1080p': form.get('use_1080p') == 'on',
        'use_1920p': form.get('use_1920p') == 'on',
        'use_sharpen': form.get('use_sharpen') == 'on',
        'sharpen_level': sharpen_level,
        'strip_metadata': form.get('strip_metadata') == 'on',
        'background_color': raw_background,
        'density': density,
        'crop_ratio': crop_ratio,
    }


def jpeg_decode_hint(width, height, use_1080p, use_1920p):
    """Target box for `-define jpeg:size=`, or None when the hint isn't safe.

    The hint makes libjpeg decode at a reduced DCT scale, so it is only sound
    for geometries expressed as an absolute bounding box: libjpeg rounds up to
    the next scale, guaranteeing the resampler still has enough pixels. It must
    NOT be combined with anything measured against the decoded image — a
    percentage resize or a pixel crop box computed from the original size would
    both silently operate on a smaller image than they were calculated for."""
    if use_1920p:
        return '1920x1920'
    if use_1080p:
        return '1080x1080'
    if width and height:
        return f'{width}x{height}'
    return None


def centered_crop_box(src_width, src_height, crop_ratio):
    """Largest centred WxH+0+0 box of the given aspect ratio, or None if the
    source dimensions aren't known."""
    if not (src_width and src_height):
        return None
    ratio_w, ratio_h = ALLOWED_CROP_RATIOS[crop_ratio]
    if src_width * ratio_h > src_height * ratio_w:
        box_h = src_height
        box_w = round(src_height * ratio_w / ratio_h)
    else:
        box_w = src_width
        box_h = round(src_width * ratio_h / ratio_w)
    return f'{max(1, box_w)}x{max(1, box_h)}+0+0'


def build_imagemagick_command(filepath, output_path, width, height, percentage, quality, keep_ratio,
                              auto_level=False, auto_gamma=False, use_1080p=False, use_1920p=False,
                              use_sharpen=False, sharpen_level='standard', strip_metadata=False,
                              background_color='white', density='', crop_ratio=''):
    """Build ImageMagick command for resizing and formatting.
    filepath must already be decoded (JXL → PNG via prepare_input_file before calling this).

    Argument order carries meaning: -density and -define are read-time settings
    and must precede the input file, -auto-orient has to run before -strip
    discards the EXIF orientation it reads, and cropping happens before -resize
    so the resize geometry applies to the final framing."""
    if not (secure_path(filepath) or is_valid_tmp_path(filepath)):
        app.logger.error("Insecure input file path detected")
        return None
    if not secure_path(output_path):
        app.logger.error("Insecure output path detected")
        return None

    # Check potrace availability for vector output formats
    ext = os.path.splitext(output_path)[1].lstrip('.').upper()
    if ext in POTRACE_FORMATS:
        potrace_check = subprocess.run(['which', 'potrace'], capture_output=True, timeout=SUBPROCESS_TIMEOUT_SHORT)
        if potrace_check.returncode != 0:
            app.logger.error(f"Output format {ext} requires potrace which is not installed")
            return None

    source_ext = os.path.splitext(filepath)[1].lower()
    command = ['magick']

    if density and source_ext in VECTOR_INPUT_EXTENSIONS:
        command.extend(['-density', density])

    # Skipped when cropping: the crop box is computed from the original
    # dimensions, so it must not run against a differently-scaled decode.
    if source_ext in {'.jpg', '.jpeg'} and not crop_ratio:
        hint = jpeg_decode_hint(width, height, use_1080p, use_1920p)
        if hint:
            # Lets libjpeg decode straight to a reduced scale rather than
            # unpacking every pixel only to throw most of them away.
            command.extend(['-define', f'jpeg:size={hint}'])

    command.append(filepath)
    command.append('-auto-orient')

    if strip_metadata:
        command.append('-strip')

    if crop_ratio in ALLOWED_CROP_RATIOS:
        src_width, src_height = get_image_dimensions(filepath)
        crop_box = centered_crop_box(src_width, src_height, crop_ratio)
        if crop_box:
            command.extend(['-gravity', 'center', '-crop', crop_box, '+repage'])

    if auto_gamma:
        command.append('-auto-gamma')
    if auto_level:
        command.append('-auto-level')

    if use_sharpen:
        sharpen_params = {
            'low': '0x0.5+0.5+0.005',
            'standard': '0x0.75+1.0+0.01',
            'high': '0x1+1.5+0.02'
        }
        sharpen_value = sharpen_params.get(sharpen_level, '1x0.5+0.02+0.0')
        app.logger.info(f"Applying sharpening with level {sharpen_level}: -unsharp {sharpen_value}")
        command.extend(['-unsharp', sharpen_value])

    if use_1920p:
        command.extend(['-resize', '1920x1920>'])

    if use_1080p:
        command.extend(['-resize', '1080x1080>'])
    else:
        if percentage:
            try:
                pct = float(percentage)
                src_width, src_height = get_image_dimensions(filepath)
                if src_width and src_height:
                    if src_width * pct / 100 > MAX_DIMENSION or src_height * pct / 100 > MAX_DIMENSION:
                        app.logger.error(f"Percentage resize ({pct}%) would exceed MAX_DIMENSION ({MAX_DIMENSION}px)")
                        return None
                resize_value = f"{pct}%"
                command.extend(['-resize', resize_value])
            except ValueError:
                return None
        elif width or height:
            try:
                if width:
                    width = int(width)
                    if width > MAX_DIMENSION:
                        app.logger.error(f"Requested width {width} exceeds MAX_DIMENSION ({MAX_DIMENSION}px)")
                        return None
                if height:
                    height = int(height)
                    if height > MAX_DIMENSION:
                        app.logger.error(f"Requested height {height} exceeds MAX_DIMENSION ({MAX_DIMENSION}px)")
                        return None

                resize_value = ''
                if width and height:
                    resize_value = f"{width}x{height}"
                    if keep_ratio:
                        resize_value += '>'
                elif width:
                    resize_value = f"{width}"
                elif height:
                    resize_value = f"x{height}"

                if resize_value:
                    command.extend(['-resize', resize_value])
            except ValueError:
                return None

    if ext in OPAQUE_OUTPUT_FORMATS:
        # These formats carry no alpha channel, so transparency has to be
        # composited onto a colour first — otherwise it is written as black.
        command.extend(['-background', background_color, '-alpha', 'remove', '-alpha', 'off'])

    if quality and quality != "100":
        try:
            quality_value = int(quality)
            if 1 <= quality_value <= 100:
                command.extend(['-quality', str(quality_value)])
        except ValueError:
            return None

    command.append(output_path)
    return command


def build_gif_create_command(input_paths, output_path, fps, width, height, loop, quality, output_format):
    """Build an ImageMagick command that assembles a sequence of already-decoded
    static images into a single animated GIF or WEBP. input_paths order is frame
    order, as chosen by the caller (route)."""
    for p in input_paths:
        if not (secure_path(p) or is_valid_tmp_path(p)):
            app.logger.error("Insecure GIF frame path detected")
            return None
    if not secure_path(output_path):
        app.logger.error("Insecure GIF output path detected")
        return None
    if output_format not in GIF_CREATE_OUTPUT_FORMATS:
        app.logger.error(f"Unsupported GIF creation output format: {output_format}")
        return None
    if width and height and (width > GIF_MAX_OUTPUT_DIMENSION or height > GIF_MAX_OUTPUT_DIMENSION):
        app.logger.error(f"Requested GIF canvas {width}x{height} exceeds GIF_MAX_OUTPUT_DIMENSION ({GIF_MAX_OUTPUT_DIMENSION}px)")
        return None

    delay_ticks = max(1, round(100 / fps))  # -delay is in 1/100s ticks
    command = ['magick', '-delay', str(delay_ticks), '-loop', str(loop)]
    command.extend(input_paths)
    # -auto-orient after the inputs applies to every frame, so a sequence shot
    # on a phone isn't assembled sideways. No -coalesce here: these are still
    # images with no frame-disposal history to flatten, and coalescing them
    # forces a full RGBA materialisation of the whole sequence. -extent below
    # is what actually normalises differing frame sizes onto one canvas.
    command.append('-auto-orient')

    if width and height:
        # -resize alone won't force a common canvas when source frames differ in
        # aspect ratio; -extent normalizes every frame onto the same canvas.
        command.extend(['-resize', f'{width}x{height}', '-gravity', 'center',
                         '-background', 'none', '-extent', f'{width}x{height}'])

    if output_format == 'GIF':
        if quality:  # reused here as palette size, 2-256
            command.extend(['-colors', str(quality)])
        command.extend(['-layers', 'optimize'])
    else:  # WEBP
        command.extend(['-quality', str(quality or 80)])

    command.append(output_path)
    return command


def build_gif_edit_command(filepath, output_path, mode, params):
    """Build an ImageMagick command for one editing operation on an existing
    animated GIF/WEBP. `params` holds mode-specific values already validated
    by the caller (route). Frame extraction has its own command builder
    (build_gif_extract_command) since its output shape differs (1 file vs N)."""
    if not (secure_path(filepath) or is_valid_tmp_path(filepath)):
        app.logger.error("Insecure GIF edit input path detected")
        return None
    if not secure_path(output_path):
        app.logger.error("Insecure GIF edit output path detected")
        return None
    if mode not in GIF_EDIT_MODES or mode == 'extract':
        return None

    if mode == 'loop':
        return ['magick', filepath, '-loop', str(params['loop']), output_path]

    command = ['magick', filepath, '-coalesce']

    if mode == 'resize':
        percentage = params.get('percentage')
        width = params.get('width')
        height = params.get('height')
        if percentage:
            command.extend(['-resize', f"{percentage}%"])
        elif width and height:
            if width > GIF_MAX_OUTPUT_DIMENSION or height > GIF_MAX_OUTPUT_DIMENSION:
                app.logger.error(f"Requested GIF resize {width}x{height} exceeds GIF_MAX_OUTPUT_DIMENSION ({GIF_MAX_OUTPUT_DIMENSION}px)")
                return None
            command.extend(['-resize', f'{width}x{height}'])
        else:
            return None
    elif mode == 'optimize':
        command.extend(['-dither', 'FloydSteinberg' if params.get('dither') else 'None'])
        command.extend(['-colors', str(params.get('colors', 256))])
    elif mode == 'speed':
        # v1 simplification: apply one uniform delay derived from the first
        # frame's original delay, rather than rescaling every frame's delay
        # individually (which -delay as a single list-form flag can't express).
        command.extend(['-delay', str(params['new_delay'])])
    elif mode == 'reverse':
        command.append('-reverse')
    elif mode == 'rotate':
        angle = params.get('angle')
        if angle:
            command.extend(['-rotate', str(angle)])
        if params.get('flip_h'):
            command.append('-flop')
        if params.get('flip_v'):
            command.append('-flip')

    if params.get('loop') is not None:
        command.extend(['-loop', str(params['loop'])])

    command.extend(['-layers', 'optimize', output_path])
    return command


def build_gif_extract_command(filepath, output_pattern, extract_mode, frame_number, frame_start, frame_end, extract_format):
    """Build an ImageMagick command to extract one frame, a range of frames, or
    every frame from an animated GIF/WEBP. frame_number/frame_start/frame_end
    must already be validated as in-range integers by the caller."""
    if not (secure_path(filepath) or is_valid_tmp_path(filepath)):
        app.logger.error("Insecure GIF extract input path detected")
        return None
    if not secure_path(output_pattern):
        app.logger.error("Insecure GIF extract output path detected")
        return None
    if extract_format not in GIF_EXTRACT_FORMATS:
        return None

    if extract_mode == 'single':
        return ['magick', f'{filepath}[{frame_number}]', output_pattern]
    elif extract_mode == 'range':
        return ['magick', f'{filepath}[{frame_start}-{frame_end}]', output_pattern]
    elif extract_mode == 'all':
        return ['magick', filepath, output_pattern]
    return None


# --- Async batch processing functions ---

def purge_old_jobs():
    """Remove completed jobs older than JOBS_TTL_HOURS from the in-memory jobs
    dict, which otherwise grows for the lifetime of the process."""
    cutoff = time.time() - JOBS_TTL_HOURS * 3600
    with jobs_lock:
        stale = [
            jid for jid, job in jobs.items()
            if job.get('status') == 'complete' and job.get('completed_at', 0) < cutoff
        ]
        for jid in stale:
            del jobs[jid]
    if stale:
        app.logger.info(f"Purged {len(stale)} completed job(s) older than {JOBS_TTL_HOURS}h")


# ImageMagick's -monitor flag reports progress on stderr as
# "<Operation>/<Type>: <offset> of <extent>, <pct>% complete", carriage-return
# terminated. Parsing it is what lets a GIF job report where it actually is
# instead of only how long it has been running. If a future ImageMagick ever
# stops matching this, nothing breaks: no line parses, no progress is reported,
# and the UI stays on its indeterminate state.
_MONITOR_LINE_RE = re.compile(
    r'^(?P<tag>.+?):\s+(?P<offset>[0-9.]+)\s+of\s+(?P<extent>[0-9.]+),\s+'
    r'(?P<pct>[0-9.]+)%\s+complete\s*$'
)

# (tag keyword, label, start%, end%) listed in pipeline execution order, so the
# overall bar only moves forward as ImageMagick walks from reading to writing.
# Reading dominates the runtime for large frames, hence its share of the range.
#
# The keywords match the tags ImageMagick actually emits, which are not named
# after the command-line options that trigger them: `-colors` reports as
# Classify/Image then Assign/Image (MagickCore/quantize.c), never "quantize".
# Missing those two is what used to freeze the bar for minutes on end — every
# event of the longest stage was silently dropped.
_MONITOR_STAGES = (
    ('load',     'Reading frames',           0, 55),
    ('coalesce', 'Aligning frames',         55, 60),
    ('resize',   'Resizing frames',         60, 68),
    ('scale',    'Resizing frames',         60, 68),
    ('extent',   'Fitting canvas',          68, 72),
    ('classify', 'Building colour palette', 72, 82),
    ('reduce',   'Building colour palette', 82, 85),
    ('assign',   'Building colour palette', 85, 90),
    ('dither',   'Building colour palette', 85, 90),
    ('kmeans',   'Building colour palette', 72, 90),
    ('quantize', 'Building colour palette', 72, 90),
    ('merge',    'Optimizing animation',    90, 95),
    ('optimize', 'Optimizing animation',    90, 95),
    ('layers',   'Optimizing animation',    90, 95),
    ('save',     'Writing file',            95, 100),
    ('write',    'Writing file',            95, 100),
    ('encode',   'Writing file',            95, 100),
)

# Some steps genuinely report nothing: OptimizeLayerFrames(), which is what
# `-layers optimize` runs, has no progress monitor at all. On a long animation
# that is minutes of real work with zero events, so the UI needs to say so
# rather than look hung.
MONITOR_IDLE_HINT_SECONDS = 20


def match_monitor_stage(tag):
    """Map an ImageMagick monitor tag onto a user-facing stage label and the
    slice of the overall progress bar it owns."""
    lowered = tag.lower()
    for keyword, label, start, end in _MONITOR_STAGES:
        if keyword in lowered:
            return label, start, end
    return None


def run_with_progress(command, timeout, on_progress):
    """Run an ImageMagick command with -monitor, feeding parsed progress events
    to on_progress(tag, fraction) as they stream in.

    Raises exactly what subprocess.run(check=True) would (CalledProcessError /
    TimeoutExpired, both carrying stderr) so callers keep their error handling.
    Progress lines are stripped out of the captured stderr, leaving only real
    warnings and errors for the message shown to the user.
    """
    monitored = [command[0], '-monitor'] + list(command[1:])
    proc = subprocess.Popen(monitored, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE, shell=False)
    timed_out = threading.Event()

    def _kill_on_timeout():
        timed_out.set()
        proc.kill()

    watchdog = threading.Timer(timeout, _kill_on_timeout)
    watchdog.start()

    stderr_lines = []
    buffer = ''
    try:
        while True:
            # os.read returns as soon as any bytes are available, unlike
            # stderr.read(n), which would hold updates back until n bytes or EOF.
            try:
                chunk = os.read(proc.stderr.fileno(), 4096)
            except OSError:
                break
            if not chunk:
                break
            buffer += chunk.decode('utf-8', errors='replace')
            parts = re.split(r'[\r\n]', buffer)
            buffer = parts.pop()
            for line in parts:
                line = line.strip()
                if not line:
                    continue
                match = _MONITOR_LINE_RE.match(line)
                if match:
                    try:
                        on_progress(match.group('tag'), float(match.group('pct')) / 100.0)
                    except Exception as e:
                        app.logger.warning(f"Progress reporting failed: {e}")
                else:
                    stderr_lines.append(line)
                    if len(stderr_lines) > 60:
                        del stderr_lines[:-40]
        returncode = proc.wait()
    finally:
        watchdog.cancel()
        try:
            proc.stderr.close()
        except Exception:
            pass
        if proc.poll() is None:
            proc.kill()

    stderr_text = '\n'.join(stderr_lines)
    if timed_out.is_set():
        raise subprocess.TimeoutExpired(monitored, timeout, stderr=stderr_text)
    if returncode != 0:
        raise subprocess.CalledProcessError(returncode, monitored, stderr=stderr_text)
    return stderr_text


def humanize_monitor_tag(tag):
    """Turn a raw monitor tag such as "Classify/Image" into "Classify", so an
    operation we have no mapping for can still be named on screen."""
    return tag.split('/')[0].strip() or tag.strip()


def make_gif_progress_reporter(job_id, total_frames):
    """Build the on_progress callback for a GIF creation job: turns raw monitor
    events into the phase/detail/percent the progress page renders."""
    state = {'frames': 0, 'percent': 0.0, 'label': '', 'pushed_at': 0.0}

    def report(tag, fraction):
        operation = humanize_monitor_tag(tag)
        stage = match_monitor_stage(tag)
        if not stage:
            # An unmapped operation is still ImageMagick doing work, so report
            # it by name and keep the bar where it is rather than dropping the
            # event and leaving the page looking frozen.
            with jobs_lock:
                job = jobs.get(job_id)
                if job:
                    job['operation'] = operation
                    job['last_event_at'] = time.time()
            return
        label, start, end = stage

        if label == 'Reading frames' and total_frames:
            # Each frame's read ends with its own 100% line, so counting those
            # gives a real "frame k of N" rather than an interpolated guess.
            in_flight = 0.0
            reading = fraction < 0.995
            if reading:
                in_flight = fraction
            else:
                state['frames'] = min(total_frames, state['frames'] + 1)
            reached = min(total_frames, state['frames'] + in_flight)
            percent = start + (end - start) * (reached / total_frames)
            # A frame that has only just started still counts as the one being
            # read, so the counter opens at "1 of N" rather than "0 of N".
            current = min(total_frames, state['frames'] + (1 if reading else 0))
            detail = f'{current} of {total_frames}'
        else:
            # Outside the reading stage the bar carries the number, so the
            # detail slot names the ImageMagick operation instead — that is
            # what tells you a long palette build is still moving.
            percent = start + (end - start) * fraction
            detail = ''

        # Never move backwards, and hold short of 100 until the job really ends.
        percent = max(state['percent'], min(99.0, percent))
        now = time.monotonic()
        if (label == state['label'] and percent - state['percent'] < 0.5
                and now - state['pushed_at'] < 0.5):
            with jobs_lock:
                job = jobs.get(job_id)
                if job:
                    job['last_event_at'] = time.time()
            return
        stage_changed = label != state['label']
        state.update({'percent': percent, 'label': label, 'pushed_at': now})

        with jobs_lock:
            job = jobs.get(job_id)
            if job:
                job['phase'] = label
                job['phase_detail'] = detail
                job['operation'] = operation
                job['percent'] = round(percent)
                job['last_event_at'] = time.time()
                if stage_changed:
                    job['stage_started_at'] = time.time()

    return report


def process_gif_create_job(job_id):
    """Process a GIF/WEBP creation job: builds one animated file from the ordered
    set of uploaded frames via a single ImageMagick invocation. Runs in a
    background daemon thread, reusing the same jobs dict + semaphore the batch
    resize pipeline uses, but as one unit of work rather than N independent ones."""
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return
        params = job['params']
        file_infos = job['files']
        output_path = job['output_path']

    with jobs_lock:
        for f in file_infos:
            f['status'] = 'processing'

    with _processing_semaphore:
        try:
            input_paths = [f['path'] for f in file_infos]
            command = build_gif_create_command(
                input_paths=input_paths,
                output_path=output_path,
                fps=params['fps'],
                width=params['width'],
                height=params['height'],
                loop=params['loop'],
                quality=params['quality'],
                output_format=params['output_format'],
            )
            if not command:
                raise RuntimeError("Could not build GIF creation command")
            app.logger.info(f"[Job {job_id}] Executing: {' '.join(command)}")
            run_with_progress(command, SUBPROCESS_TIMEOUT_LONG,
                              make_gif_progress_reporter(job_id, len(file_infos)))
        except subprocess.CalledProcessError as e:
            app.logger.error(f"[Job {job_id}] GIF creation error: {e.stderr}")
            error_msg = classify_processing_error(e, e.stderr)
            with jobs_lock:
                for f in file_infos:
                    f['status'] = 'error'
                    f['error'] = error_msg
                jobs[job_id]['errors'] = len(file_infos)
        except Exception as e:
            app.logger.error(f"[Job {job_id}] GIF creation error: {e}")
            error_msg = classify_processing_error(e, getattr(e, 'stderr', ''))
            with jobs_lock:
                for f in file_infos:
                    f['status'] = 'error'
                    f['error'] = error_msg
                jobs[job_id]['errors'] = len(file_infos)
        else:
            with jobs_lock:
                for f in file_infos:
                    f['status'] = 'done'
                jobs[job_id]['done'] = len(file_infos)
                jobs[job_id]['phase'] = 'Complete'
                jobs[job_id]['phase_detail'] = ''
                jobs[job_id]['percent'] = 100
            for f in file_infos:
                try:
                    src = secure_path(f['path'])
                    if src and os.path.exists(src):
                        os.remove(src)
                except Exception as e:
                    app.logger.warning(f"[Job {job_id}] Could not remove source frame {f['path']}: {e}")

    with jobs_lock:
        jobs[job_id]['status'] = 'complete'
        jobs[job_id]['completed_at'] = time.time()

    app.logger.info(f"Job {job_id} (gif_create) complete")


def process_job(job_id):
    """Process all files for a batch job. Runs in a background daemon thread."""
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return
        file_list = job['files']
        params = job['params']
        batch_folder = job['batch_folder']
        timestamp = job['timestamp']

    futures = {
        executor.submit(process_single_file, job_id, file_info, params, batch_folder): file_info
        for file_info in file_list
    }

    for future in as_completed(futures):
        try:
            future.result()
        except Exception as e:
            app.logger.error(f"Unexpected error in batch future for job {job_id}: {e}")

    # Create ZIP from all successfully processed files
    with jobs_lock:
        done = jobs[job_id]['done']

    if done > 0:
        zip_filename = f'ImaGUIck_{timestamp}.zip'
        zip_path = os.path.join(app.config['OUTPUT_FOLDER'], zip_filename)
        try:
            with ZipFile(zip_path, 'w') as zipf:
                with jobs_lock:
                    for fi in jobs[job_id]['files']:
                        if fi.get('output') and os.path.exists(fi['output']):
                            zipf.write(fi['output'], os.path.basename(fi['output']))
            with jobs_lock:
                jobs[job_id]['zip'] = zip_filename
            app.logger.info(f"ZIP created for job {job_id}: {zip_filename}")
        except Exception as e:
            app.logger.error(f"Error creating ZIP for job {job_id}: {e}")

    with jobs_lock:
        jobs[job_id]['status'] = 'complete'
        jobs[job_id]['completed_at'] = time.time()
        final_done = jobs[job_id]['done']
        final_errors = jobs[job_id]['errors']

    app.logger.info(f"Job {job_id} complete: {final_done} done, {final_errors} errors")


def process_single_file(job_id, file_info, params, batch_folder):
    """Process one file within a batch job. Acquires semaphore before ImageMagick."""
    with _processing_semaphore:
        with jobs_lock:
            file_info['status'] = 'processing'

        filepath = file_info['path']
        fname = file_info['original']

        try:
            output_format = params['output_format']
            if output_format:
                output_filename = f'{os.path.splitext(fname)[0]}_imaGUIck.{output_format.lower()}'
            else:
                output_filename = f'{os.path.splitext(fname)[0]}_imaGUIck{os.path.splitext(fname)[1]}'
            output_path = os.path.join(batch_folder, output_filename)

            width, height = resolve_missing_dimension(
                params['width'], params['height'], params['keep_ratio'], filepath
            )

            input_path, tmp_path = prepare_input_file(filepath)
            try:
                command = build_imagemagick_command(
                    filepath=input_path,
                    output_path=output_path,
                    width=width,
                    height=height,
                    percentage=params['percentage'],
                    quality=params['quality'],
                    keep_ratio=params['keep_ratio'],
                    auto_level=params['auto_level'],
                    auto_gamma=params['auto_gamma'],
                    use_1080p=params['use_1080p'],
                    use_1920p=params['use_1920p'],
                    use_sharpen=params['use_sharpen'],
                    sharpen_level=params['sharpen_level'],
                    strip_metadata=params['strip_metadata'],
                    background_color=params['background_color'],
                    density=params['density'],
                    crop_ratio=params['crop_ratio'],
                )
                if not command:
                    raise RuntimeError(f"Could not build ImageMagick command for {fname}")

                app.logger.info(f"[Job {job_id}] Executing: {' '.join(command)}")
                subprocess.run(command, check=True, capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_LONG)
            except subprocess.CalledProcessError as e:
                app.logger.error(f"[Job {job_id}] ImageMagick error for {fname}: {e.stderr}")
                raise
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    os.remove(tmp_path)

            # Clean up source file after successful processing
            try:
                src = secure_path(filepath)
                if src and os.path.exists(src):
                    os.remove(src)
            except Exception as e:
                app.logger.warning(f"[Job {job_id}] Could not remove source file {filepath}: {e}")

            with jobs_lock:
                file_info['status'] = 'done'
                file_info['output'] = output_path
                jobs[job_id]['done'] += 1

        except Exception as e:
            app.logger.error(f"[Job {job_id}] Error processing {fname}: {e}")
            with jobs_lock:
                file_info['status'] = 'error'
                file_info['error'] = classify_processing_error(e, getattr(e, 'stderr', ''))
                jobs[job_id]['errors'] += 1


# --- Routes ---

@app.route('/')
def index():
    """Homepage with upload options."""
    return render_template('index.html')


@app.route('/health')
def health():
    """Health check endpoint."""
    with jobs_lock:
        active = sum(1 for j in jobs.values() if j.get('status') != 'complete')
    return {'status': 'ok', 'active_jobs': active}, 200


@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file uploads. Supports both regular form POST and XHR (returns JSON).
    The optional `intent` field routes to the GIF/WEBP creation flow instead of
    the default resize flow; the save loop itself is shared by both."""
    is_xhr = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    intent = request.form.get('intent', 'resize')

    def _error(msg, status=400):
        if is_xhr:
            return {'error': msg}, status
        flash(msg, 'error')
        return redirect(url_for('index'))

    if 'file' not in request.files:
        return _error('No file selected')

    files = request.files.getlist('file')
    if not files or all(f.filename == '' for f in files):
        return _error('Please select at least one file')

    uploaded_files = []
    errors = []
    for file in files:
        if not file or not file.filename:
            continue
        if not allowed_file(file.filename):
            errors.append(f"Unsupported format: {safe_display_filename(file.filename)}")
            continue
        unique_name = f"{uuid.uuid4().hex}_{safe_display_filename(file.filename)}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
        file.save(filepath)
        # Per-file size check after saving
        if os.path.getsize(filepath) > PER_FILE_MAX_SIZE:
            os.remove(filepath)
            errors.append(
                f"{safe_display_filename(file.filename)} exceeds the per-file limit of "
                f"{PER_FILE_MAX_SIZE // 1024 // 1024} MB"
            )
            continue
        uploaded_files.append(unique_name)

    for err in errors:
        flash(err, 'error')

    if not uploaded_files:
        msg = errors[0] if errors else 'No valid file'
        return _error(msg)

    if intent == 'gif_create' and len(uploaded_files) == 1:
        # One animated file can only mean editing, never assembling, so the
        # GIF tab routes it to the editor instead of dead-ending on "at least
        # 2 images" — which is what made that whole page hard to find.
        single_path = secure_path(os.path.join(app.config['UPLOAD_FOLDER'], uploaded_files[0]))
        if not (single_path and is_animated_file(single_path)):
            return _error('Select at least 2 images to build an animation, '
                          'or upload a single animated GIF/WEBP to edit it')
        redirect_url = url_for('gif_edit_options', filename=uploaded_files[0])
    elif intent == 'gif_create':
        # Creation always goes through upload_sessions (even for 2 files),
        # since frame order matters and the query string can't carry it safely.
        upload_key = uuid.uuid4().hex
        with upload_sessions_lock:
            upload_sessions[upload_key] = uploaded_files
        redirect_url = url_for('gif_create_options', upload_key=upload_key)
    elif len(uploaded_files) == 1:
        redirect_url = url_for('resize_options', filename=uploaded_files[0])
    else:
        # Store filenames server-side to avoid the URL length limit (Gunicorn's --limit-request-line 8190)
        upload_key = uuid.uuid4().hex
        with upload_sessions_lock:
            upload_sessions[upload_key] = uploaded_files
        redirect_url = url_for('resize_batch_options', upload_key=upload_key)

    if is_xhr:
        return {'redirect': redirect_url}
    return redirect(redirect_url)


@app.route('/upload_url', methods=['POST'])
def upload_url():
    """Handle image upload from a URL."""
    url = request.form.get('url', '').strip()

    if not url:
        flash('No URL provided', 'error')
        return redirect(url_for('index'))

    if not is_safe_url(url):
        flash('Invalid or unsafe URL', 'error')
        return redirect(url_for('index'))

    # Reconstruct URL from parsed components so that only the validated
    # scheme/host/path are forwarded — no fragment, no unexpected schemes.
    _parsed = urlparse(url)
    safe_url = urlunparse((
        _parsed.scheme.lower(), _parsed.netloc, _parsed.path,
        _parsed.params, _parsed.query, ''
    ))

    try:
        response = requests.get(safe_url, timeout=30, stream=True, allow_redirects=False)
        response.raise_for_status()

        content_type = response.headers.get('content-type', '').lower()
        if not content_type.startswith('image/'):
            raise ValueError('Not an image file')

        filename = safe_display_filename(os.path.basename(url.split('?')[0]))
        if not filename or not allowed_file(filename):
            raise ValueError('Invalid file type')

        unique_name = f"{uuid.uuid4().hex}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)

        downloaded = 0
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=65536):
                downloaded += len(chunk)
                if downloaded > MAX_FILE_SIZE:
                    f.close()
                    os.remove(filepath)
                    raise ValueError(f'File too large (max {MAX_FILE_SIZE // 1024 // 1024} MB)')
                f.write(chunk)

        return redirect(url_for('resize_options', filename=unique_name))

    except Exception as e:
        flash(f'Error downloading image: {str(e)}', 'error')
        return redirect(url_for('index'))


@app.route('/resize_options/<filename>')
def resize_options(filename):
    """Resize options page for a single image."""
    sanitized_filename = safe_display_filename(os.path.basename(filename))
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], sanitized_filename)
    if not os.path.exists(filepath):
        flash_error("File not found.")
        return redirect(url_for('index'))

    dimensions = get_image_dimensions(filepath)
    if not dimensions or dimensions == (None, None):
        flash('Image too large or unsupported (max 10000px per side)', 'error')
        return redirect(url_for('index'))

    formats = get_available_formats(filepath)
    image_type = analyze_image_type(filepath)

    app.logger.info(f"Formats passed to template: {formats}")
    return render_template('resize.html',
                           filename=sanitized_filename,
                           width=dimensions[0],
                           height=dimensions[1],
                           formats=formats,
                           image_type=image_type,
                           defaults=DEFAULTS)


@app.route('/resize/<filename>', methods=['POST'])
def resize_image(filename):
    """Handle resizing or format conversion for a single image."""
    filename = safe_display_filename(os.path.basename(filename))
    if is_unsafe_filename(filename):
        flash('Invalid filename')
        return render_template('result.html',
                               success=False,
                               title='Error',
                               return_url=url_for('index'))
    try:
        width = request.form.get('width', '')
        height = request.form.get('height', '')
        keep_ratio = request.form.get('keep_ratio') == 'on'
        raw_format = request.form.get('format', '').upper().strip()
        output_format = raw_format if raw_format in ALLOWED_OUTPUT_FORMATS else ''
        auto_level = request.form.get('auto_level') == 'on'
        auto_gamma = request.form.get('auto_gamma') == 'on'
        use_sharpen = request.form.get('use_sharpen') == 'on'
        raw_sharpen = request.form.get('sharpen_level', 'standard').strip().lower()
        sharpen_level = raw_sharpen if raw_sharpen in ALLOWED_SHARPEN_LEVELS else 'standard'
        # Reused rather than re-read field by field, so the allowlisting of the
        # newer options lives in exactly one place.
        options = extract_processing_params(request.form)

        app.logger.info(f"Processing resize request for {filename}")
        app.logger.info(f"Sharpening: enabled={use_sharpen}, level={sharpen_level}")
        app.logger.info(f"Initial parameters: width={width}, height={height}, keep_ratio={keep_ratio}")

        filepath = secure_path(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        if not filepath or not os.path.exists(filepath):
            flash('File not found')
            return render_template('result.html',
                                   success=False,
                                   title='Error',
                                   return_url=url_for('resize_options', filename=filename))

        width, height = resolve_missing_dimension(width, height, keep_ratio, filepath)
        app.logger.info(f"Final parameters: width={width}, height={height}, format={output_format}")

        # Strip UUID prefix (32 hex chars + underscore) to restore original filename
        clean_name = re.sub(r'^[a-f0-9]{32}_', '', filename)
        base_name = os.path.splitext(clean_name)[0]
        if output_format:
            output_filename = f"{base_name}_imaGUIck.{output_format.lower()}"
        else:
            output_filename = f"{base_name}_imaGUIck{os.path.splitext(clean_name)[1]}"

        output_filename = safe_display_filename(output_filename)
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)
        app.logger.info(f"Output path: {output_path}")

        input_path, tmp_path = prepare_input_file(filepath)
        try:
            command = build_imagemagick_command(
                filepath=input_path,
                output_path=output_path,
                width=width,
                height=height,
                percentage=request.form.get('percentage', DEFAULTS["percentage"]),
                quality=request.form.get('quality', DEFAULTS["quality"]),
                keep_ratio=keep_ratio,
                auto_level=auto_level,
                auto_gamma=auto_gamma,
                use_1080p=request.form.get('use_1080p') == 'on',
                use_1920p=request.form.get('use_1920p') == 'on',
                use_sharpen=use_sharpen,
                sharpen_level=sharpen_level,
                strip_metadata=options['strip_metadata'],
                background_color=options['background_color'],
                density=options['density'],
                crop_ratio=options['crop_ratio'],
            )

            if not command:
                flash('Error preparing resize command')
                return render_template('result.html',
                                       success=False,
                                       title='Error',
                                       return_url=url_for('resize_options', filename=filename))

            app.logger.info(f"Executing command: {' '.join(command)}")
            subprocess.run(command, check=True, capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_MEDIUM)
        except subprocess.CalledProcessError as e:
            app.logger.error(f"ImageMagick error for {filename}: {e.stderr}")
            flash(classify_processing_error(e, e.stderr))
            return render_template('result.html',
                                   success=False,
                                   title='Error',
                                   return_url=url_for('resize_options', filename=filename))
        except subprocess.TimeoutExpired as e:
            app.logger.error(f"Timeout processing {filename}")
            flash(classify_processing_error(e))
            return render_template('result.html',
                                   success=False,
                                   title='Error',
                                   return_url=url_for('resize_options', filename=filename))
        finally:
            if tmp_path and is_valid_tmp_path(tmp_path) and os.path.exists(tmp_path):
                os.remove(tmp_path)

        flash('Image processed successfully!')
        return render_template('result.html',
                               success=True,
                               title='Success',
                               filename=output_filename,
                               batch=False)

    except Exception as e:
        app.logger.error(f"Error during resize: {str(e)}")
        flash(classify_processing_error(e))
        return render_template('result.html',
                               success=False,
                               title='Error',
                               return_url=url_for('resize_options', filename=filename) if filename else url_for('index'))


@app.route('/resize_batch_options')
def resize_batch_options(filenames=None):
    """Resize options page for batch processing."""
    if not filenames:
        upload_key = request.args.get('upload_key')
        if upload_key:
            with upload_sessions_lock:
                filenames = upload_sessions.get(upload_key, [])
        else:
            # Legacy fallback: filenames in query string — sanitize each entry
            filenames = [
                safe_display_filename(os.path.basename(f.strip()))
                for f in request.args.get('filenames', '').split(',')
                if f.strip()
            ]

    if not filenames or not filenames[0]:
        return redirect(url_for('index'))

    batch_info = {
        'has_transparency': False,
        'has_photos': False,
        'has_graphics': False,
        'total_files': len(filenames)
    }

    image_types = []
    first_file_path = None

    for filename in filenames:
        filename = safe_display_filename(os.path.basename(filename))
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if not os.path.exists(filepath):
            continue

        if first_file_path is None:
            first_file_path = filepath

        image_type = analyze_image_type(filepath)
        if image_type:
            if image_type.get('has_transparency'):
                batch_info['has_transparency'] = True
            if image_type.get('is_photo'):
                batch_info['has_photos'] = True
            if not image_type.get('is_photo'):
                batch_info['has_graphics'] = True

            image_types.append({
                'filename': filename,
                'type': image_type
            })

    formats = get_available_formats(first_file_path)

    return render_template('resize_batch.html',
                           files=filenames,
                           formats=formats,
                           batch_info=batch_info,
                           image_types=image_types,
                           defaults=DEFAULTS)


@app.route('/resize_batch', methods=['POST'])
def resize_batch():
    """Submit batch for async processing. Returns immediately with a job ID and redirects to progress page."""
    if 'filenames' not in request.form:
        flash('No files selected')
        return render_template('result.html',
                               success=False,
                               title='Error',
                               return_url=url_for('index'))

    filenames = [f.strip() for f in request.form['filenames'].split(',') if f.strip()]
    if not filenames:
        flash('No files selected')
        return render_template('result.html',
                               success=False,
                               title='Error',
                               return_url=url_for('index'))

    params = extract_processing_params(request.form)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    batch_folder = os.path.join(app.config['OUTPUT_FOLDER'], f'batch_{timestamp}')
    os.makedirs(batch_folder, exist_ok=True)

    file_list = []
    for fname in filenames:
        fname = safe_display_filename(os.path.basename(fname))
        fpath = secure_path(os.path.join(app.config['UPLOAD_FOLDER'], fname))
        if fpath and os.path.isfile(fpath):
            # Strip UUID prefix (32 hex chars + underscore) to restore original filename
            original_name = re.sub(r'^[a-f0-9]{32}_', '', fname)
            file_list.append({
                'original': original_name,
                'path': fpath,
                'output': None,
                'status': 'queued',
                'error': None
            })

    if not file_list:
        flash('No valid files found')
        return render_template('result.html',
                               success=False,
                               title='Error',
                               return_url=url_for('index'))

    purge_old_jobs()

    job_id = uuid.uuid4().hex
    with jobs_lock:
        jobs[job_id] = {
            'kind': 'batch',
            'files': file_list,
            'params': params,
            'batch_folder': batch_folder,
            'timestamp': timestamp,
            'zip': None,
            'total': len(file_list),
            'done': 0,
            'errors': 0,
            'status': 'processing',
            'created_at': time.time(),
        }

    t = threading.Thread(target=process_job, args=(job_id,), daemon=True)
    t.start()

    return redirect(url_for('job_progress', job_id=job_id))


@app.route('/gif_create_options')
def gif_create_options():
    """Options page for creating an animated GIF/WEBP from a sequence of already-uploaded images."""
    upload_key = request.args.get('upload_key')
    filenames = []
    if upload_key:
        with upload_sessions_lock:
            filenames = upload_sessions.get(upload_key, [])

    if not filenames:
        flash('No files selected', 'error')
        return redirect(url_for('index'))

    if len(filenames) < 2:
        flash('Select at least 2 images to create an animation', 'error')
        return redirect(url_for('index'))

    if len(filenames) > GIF_MAX_FRAMES:
        flash(f'Too many images ({len(filenames)}). Maximum is {GIF_MAX_FRAMES} frames.', 'error')
        return redirect(url_for('index'))

    valid_files = []
    for filename in filenames:
        filename = safe_display_filename(os.path.basename(filename))
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(filepath):
            valid_files.append(filename)

    if len(valid_files) < 2:
        flash('No valid files found', 'error')
        return redirect(url_for('index'))

    # RAW/JXL frames need the dcraw/djxl pre-decode step that prepare_input_file()
    # provides for the resize pipeline; GIF creation passes frames to ImageMagick
    # directly, so these formats aren't supported as animation frames yet.
    unsupported = [f for f in valid_files if os.path.splitext(f)[1].lower() in (RAW_FORMATS_DCRAW | {'.jxl'})]
    if unsupported:
        flash('RAW and JXL files are not supported as animation frames yet. Please select only standard image formats.', 'error')
        return redirect(url_for('index'))

    return render_template('gif_create.html',
                           files=valid_files,
                           upload_key=upload_key,
                           webp_supported=webp_animation_supported(),
                           gif_max_frames=GIF_MAX_FRAMES,
                           gif_max_dimension=GIF_MAX_OUTPUT_DIMENSION)


@app.route('/gif_create', methods=['POST'])
def gif_create():
    """Submit a GIF/WEBP creation job. Validates frame count and combined pixel
    budget before touching the filesystem or spawning any processing, then
    reuses the same async job/SSE progress page as batch resize."""
    upload_key = request.form.get('upload_key', '')
    with upload_sessions_lock:
        filenames = upload_sessions.get(upload_key, [])

    if not filenames:
        flash('No files selected', 'error')
        return redirect(url_for('index'))

    if len(filenames) > GIF_MAX_FRAMES:
        flash(f'Too many images. Maximum is {GIF_MAX_FRAMES} frames.', 'error')
        return redirect(url_for('index'))

    if any(os.path.splitext(f)[1].lower() in (RAW_FORMATS_DCRAW | {'.jxl'}) for f in filenames):
        flash('RAW and JXL files are not supported as animation frames yet.', 'error')
        return redirect(url_for('index'))

    try:
        fps = max(1, min(30, int(request.form.get('fps', 12))))
    except ValueError:
        fps = 12

    try:
        loop = max(0, min(100, int(request.form.get('loop', 0))))
    except ValueError:
        loop = 0

    quality = None
    quality_raw = request.form.get('quality', '').strip()
    if quality_raw:
        try:
            quality = int(quality_raw)
        except ValueError:
            quality = None

    raw_format = request.form.get('output_format', 'GIF').upper().strip()
    output_format = raw_format if raw_format in GIF_CREATE_OUTPUT_FORMATS else 'GIF'
    if output_format == 'WEBP' and not webp_animation_supported():
        flash('Animated WEBP is not supported on this server. Use GIF instead.', 'error')
        return redirect(url_for('gif_create_options', upload_key=upload_key))

    width = height = None
    w_raw = request.form.get('width', '').strip()
    h_raw = request.form.get('height', '').strip()
    if w_raw.isdigit() and h_raw.isdigit():
        width, height = int(w_raw), int(h_raw)
    elif w_raw.isdigit() or h_raw.isdigit():
        # Only one dimension given — scale the other proportionally from the
        # first frame's own aspect ratio, mirroring resolve_missing_dimension()
        # in the single-image resize flow, instead of silently dropping it.
        first_fname = safe_display_filename(os.path.basename(filenames[0]))
        first_fpath = secure_path(os.path.join(app.config['UPLOAD_FOLDER'], first_fname))
        first_w, first_h = get_image_dimensions(first_fpath) if first_fpath else (None, None)
        if first_w and first_h:
            if w_raw.isdigit():
                width = int(w_raw)
                height = round(width * first_h / first_w)
            else:
                height = int(h_raw)
                width = round(height * first_w / first_h)

    if width and height and (width > GIF_MAX_OUTPUT_DIMENSION or height > GIF_MAX_OUTPUT_DIMENSION):
        flash(f'Canvas size too large. Maximum is {GIF_MAX_OUTPUT_DIMENSION}px per side.', 'error')
        return redirect(url_for('gif_create_options', upload_key=upload_key))

    file_list = []
    total_pixels = 0
    for fname in filenames:
        fname = safe_display_filename(os.path.basename(fname))
        fpath = secure_path(os.path.join(app.config['UPLOAD_FOLDER'], fname))
        if not fpath or not os.path.isfile(fpath):
            continue
        frame_w, frame_h = get_image_dimensions(fpath)
        if not frame_w or not frame_h:
            flash(f'Could not read dimensions for {fname}', 'error')
            return redirect(url_for('gif_create_options', upload_key=upload_key))
        total_pixels += frame_w * frame_h
        if total_pixels > GIF_MAX_TOTAL_PIXELS:
            flash('Combined frame size is too large for a single animation.', 'error')
            return redirect(url_for('gif_create_options', upload_key=upload_key))
        original_name = re.sub(r'^[a-f0-9]{32}_', '', fname)
        file_list.append({
            'original': original_name,
            'path': fpath,
            'output': None,
            'status': 'queued',
            'error': None
        })

    if len(file_list) < 2:
        flash('At least 2 valid images are required', 'error')
        return redirect(url_for('index'))

    purge_old_jobs()

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    base_name = os.path.splitext(safe_display_filename(re.sub(r'^[a-f0-9]{32}_', '', filenames[0])))[0]
    output_filename = safe_display_filename(f'{base_name}_imaGUIck_{timestamp}.{output_format.lower()}')
    output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)

    job_id = uuid.uuid4().hex
    with jobs_lock:
        jobs[job_id] = {
            'kind': 'gif_create',
            'files': file_list,
            'params': {
                'fps': fps,
                'width': width,
                'height': height,
                'loop': loop,
                'quality': quality,
                'output_format': output_format,
            },
            'output_path': output_path,
            'output_filename': output_filename,
            'zip': None,
            'total': len(file_list),
            'done': 0,
            'errors': 0,
            'status': 'processing',
            'phase': 'Starting',
            'phase_detail': '',
            'operation': '',
            'percent': 0,
            'stage_started_at': time.time(),
            'last_event_at': time.time(),
            'created_at': time.time(),
        }

    t = threading.Thread(target=process_gif_create_job, args=(job_id,), daemon=True)
    t.start()

    with upload_sessions_lock:
        upload_sessions.pop(upload_key, None)

    return redirect(url_for('job_progress', job_id=job_id))


@app.route('/gif_edit_options/<filename>')
def gif_edit_options(filename):
    """Options page for editing an existing animated GIF/WEBP."""
    sanitized_filename = safe_display_filename(os.path.basename(filename))
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], sanitized_filename)
    if not os.path.exists(filepath):
        flash_error("File not found.")
        return redirect(url_for('index'))

    validated_path = secure_path(filepath)
    try:
        with Image.open(validated_path) as img:
            is_animated = getattr(img, 'is_animated', False)
            n_frames = getattr(img, 'n_frames', 1)
    except Exception as e:
        app.logger.error(f"Error opening {filename} for GIF edit: {e}")
        flash('Could not read this file.', 'error')
        return redirect(url_for('index'))

    if not is_animated:
        flash('This file is not an animated GIF/WEBP.', 'error')
        return redirect(url_for('resize_options', filename=sanitized_filename))

    dimensions = get_image_dimensions(filepath)

    return render_template('gif_edit.html',
                           filename=sanitized_filename,
                           n_frames=n_frames,
                           width=dimensions[0],
                           height=dimensions[1],
                           webp_supported=webp_animation_supported(),
                           gif_max_dimension=GIF_MAX_OUTPUT_DIMENSION)


@app.route('/gif_edit/<filename>', methods=['POST'])
def gif_edit(filename):
    """Handle one editing operation on an existing animated GIF/WEBP. Synchronous,
    mirroring resize_image()'s pattern since edits are single-file and bounded
    (unlike GIF creation, which can involve many large input frames)."""
    filename = safe_display_filename(os.path.basename(filename))
    if is_unsafe_filename(filename):
        flash('Invalid filename')
        return render_template('result.html', success=False, title='Error',
                               return_url=url_for('index'))

    mode = request.form.get('mode', '').strip().lower()
    if mode not in GIF_EDIT_MODES:
        flash('Invalid edit mode')
        return render_template('result.html', success=False, title='Error',
                               return_url=url_for('gif_edit_options', filename=filename))

    try:
        filepath = secure_path(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        if not filepath or not os.path.exists(filepath):
            flash('File not found')
            return render_template('result.html', success=False, title='Error',
                                   return_url=url_for('index'))

        clean_name = re.sub(r'^[a-f0-9]{32}_', '', filename)
        base_name, orig_ext = os.path.splitext(clean_name)
        orig_ext = orig_ext.lstrip('.').upper() or 'GIF'
        if orig_ext not in GIF_CREATE_OUTPUT_FORMATS:
            orig_ext = 'GIF'

        raw_loop = request.form.get('loop', '').strip()
        loop = None
        if raw_loop:
            try:
                loop = max(0, min(100, int(raw_loop)))
            except ValueError:
                loop = None
        if mode == 'loop' and loop is None:
            loop = 0  # 0 = infinite, a sensible default if parsing failed

        if mode == 'extract':
            extract_mode = request.form.get('extract_mode', 'single').strip().lower()
            if extract_mode not in ('single', 'range', 'all'):
                extract_mode = 'single'
            raw_extract_format = request.form.get('extract_format', 'PNG').upper().strip()
            extract_format = raw_extract_format if raw_extract_format in GIF_EXTRACT_FORMATS else 'PNG'

            try:
                with Image.open(filepath) as img:
                    n_frames = getattr(img, 'n_frames', 1)
            except Exception:
                n_frames = 1

            try:
                frame_number = max(0, min(n_frames - 1, int(request.form.get('frame_number', 0))))
                frame_start = max(0, min(n_frames - 1, int(request.form.get('frame_start', 0))))
                frame_end = max(frame_start, min(n_frames - 1, int(request.form.get('frame_end', n_frames - 1))))
            except ValueError:
                flash('Invalid frame number')
                return render_template('result.html', success=False, title='Error',
                                       return_url=url_for('gif_edit_options', filename=filename))

            if extract_mode == 'single':
                output_filename = safe_display_filename(f'{base_name}_frame{frame_number}_imaGUIck.{extract_format.lower()}')
                output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)
                command = build_gif_extract_command(filepath, output_path, extract_mode,
                                                     frame_number, frame_start, frame_end, extract_format)
            else:
                zip_dir_name = safe_display_filename(f'{base_name}_frames_{uuid.uuid4().hex[:8]}')
                zip_dir = os.path.join(app.config['OUTPUT_FOLDER'], zip_dir_name)
                os.makedirs(zip_dir, exist_ok=True)
                output_pattern = os.path.join(zip_dir, f'frame_%03d.{extract_format.lower()}')
                command = build_gif_extract_command(filepath, output_pattern, extract_mode,
                                                     frame_number, frame_start, frame_end, extract_format)

            if not command:
                flash('Error preparing extraction command')
                return render_template('result.html', success=False, title='Error',
                                       return_url=url_for('gif_edit_options', filename=filename))

            app.logger.info(f"Executing: {' '.join(command)}")
            subprocess.run(command, check=True, capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_MEDIUM)

            if extract_mode == 'single':
                flash('Frame extracted successfully!')
                return render_template('result.html', success=True, title='Success',
                                       filename=output_filename, batch=False)
            else:
                zip_filename = safe_display_filename(f'{zip_dir_name}.zip')
                zip_path = os.path.join(app.config['OUTPUT_FOLDER'], zip_filename)
                with ZipFile(zip_path, 'w') as zipf:
                    for fn in sorted(os.listdir(zip_dir)):
                        zipf.write(os.path.join(zip_dir, fn), fn)
                shutil.rmtree(zip_dir, ignore_errors=True)
                flash('Frames extracted successfully!')
                return render_template('result.html', success=True, title='Success',
                                       filename=zip_filename, batch=True)

        # Non-extract modes: produce a single animated output file
        raw_format = request.form.get('output_format', orig_ext).upper().strip()
        output_format = raw_format if raw_format in GIF_CREATE_OUTPUT_FORMATS else orig_ext
        if output_format == 'WEBP' and not webp_animation_supported():
            flash('Animated WEBP is not supported on this server. Use GIF instead.')
            return render_template('result.html', success=False, title='Error',
                                   return_url=url_for('gif_edit_options', filename=filename))

        output_filename = safe_display_filename(f'{base_name}_imaGUIck.{output_format.lower()}')
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)

        params = {'loop': loop}

        if mode == 'resize':
            percentage_raw = request.form.get('percentage', '').strip()
            width_raw = request.form.get('width', '').strip()
            height_raw = request.form.get('height', '').strip()
            if percentage_raw:
                try:
                    params['percentage'] = float(percentage_raw)
                except ValueError:
                    params['percentage'] = None
            elif width_raw.isdigit() and height_raw.isdigit():
                edit_width, edit_height = int(width_raw), int(height_raw)
                if edit_width > GIF_MAX_OUTPUT_DIMENSION or edit_height > GIF_MAX_OUTPUT_DIMENSION:
                    flash(f'Size too large. Maximum is {GIF_MAX_OUTPUT_DIMENSION}px per side.')
                    return render_template('result.html', success=False, title='Error',
                                           return_url=url_for('gif_edit_options', filename=filename))
                params['width'] = edit_width
                params['height'] = edit_height
        elif mode == 'optimize':
            try:
                params['colors'] = max(2, min(256, int(request.form.get('colors', 256))))
            except ValueError:
                params['colors'] = 256
            params['dither'] = request.form.get('dither') == 'on'
        elif mode == 'speed':
            try:
                speed_factor = max(0.1, min(10, float(request.form.get('speed_factor', 1.0))))
            except ValueError:
                speed_factor = 1.0
            base_delay = 10
            try:
                with Image.open(filepath) as img:
                    base_delay = (img.info.get('duration', 100) // 10) or 10
            except Exception:
                pass
            params['new_delay'] = max(2, round(base_delay / speed_factor))
        elif mode == 'rotate':
            angle_raw = request.form.get('angle', '')
            if angle_raw in ('90', '180', '270'):
                params['angle'] = int(angle_raw)
            params['flip_h'] = request.form.get('flip_h') == 'on'
            params['flip_v'] = request.form.get('flip_v') == 'on'

        command = build_gif_edit_command(filepath, output_path, mode, params)
        if not command:
            flash('Error preparing edit command')
            return render_template('result.html', success=False, title='Error',
                                   return_url=url_for('gif_edit_options', filename=filename))

        app.logger.info(f"Executing: {' '.join(command)}")
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_MEDIUM)

        flash('Animation processed successfully!')
        return render_template('result.html', success=True, title='Success',
                               filename=output_filename, batch=False)

    except subprocess.CalledProcessError as e:
        app.logger.error(f"GIF edit error for {filename}: {e.stderr}")
        flash(classify_processing_error(e, e.stderr))
        return render_template('result.html', success=False, title='Error',
                               return_url=url_for('gif_edit_options', filename=filename))
    except subprocess.TimeoutExpired as e:
        app.logger.error(f"Timeout editing {filename}")
        flash(classify_processing_error(e))
        return render_template('result.html', success=False, title='Error',
                               return_url=url_for('gif_edit_options', filename=filename))
    except Exception as e:
        app.logger.error(f"Error during GIF edit: {str(e)}")
        flash(classify_processing_error(e))
        return render_template('result.html', success=False, title='Error',
                               return_url=url_for('gif_edit_options', filename=filename) if filename else url_for('index'))


@app.route('/job/<job_id>/progress')
def job_progress(job_id):
    """Progress page for a batch job."""
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        flash('Job not found', 'error')
        return redirect(url_for('index'))
    return render_template('progress.html', job_id=job_id, total=job['total'],
                           job_kind=job.get('kind', 'batch'),
                           idle_hint_seconds=MONITOR_IDLE_HINT_SECONDS)


@app.route('/job/<job_id>/status')
def job_status(job_id):
    """SSE endpoint streaming real-time job status."""
    purge_old_jobs()

    def generate():
        while True:
            with jobs_lock:
                job = jobs.get(job_id)
                if not job:
                    yield 'data: {"error": "job not found"}\n\n'
                    return
                payload = {
                    'kind': job.get('kind', 'batch'),
                    'total': job['total'],
                    'done': job['done'],
                    'errors': job['errors'],
                    'files': [
                        {
                            'name': f['original'],
                            'status': f['status'],
                            'error': f.get('error')
                        }
                        for f in job['files']
                    ],
                    'zip': job.get('zip'),
                    'output': job.get('output_filename'),
                    'phase': job.get('phase'),
                    'phase_detail': job.get('phase_detail'),
                    'operation': job.get('operation'),
                    'percent': job.get('percent'),
                    # Computed here rather than sent as timestamps, so the page
                    # never has to trust that the browser clock agrees with the
                    # server's. These are what show the job is alive while a
                    # silent step like `-layers optimize` is running.
                    'stage_seconds': int(time.time() - job.get('stage_started_at', time.time())),
                    'idle_seconds': int(time.time() - job.get('last_event_at', time.time())),
                    'complete': job.get('status') == 'complete'
                }
            yield f'data: {json.dumps(payload)}\n\n'
            if payload['complete']:
                return
            time.sleep(0.5)

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )


@app.route('/download_batch/<filename>')
def download_batch(filename):
    """Serve the ZIP file for download."""
    safe_name = safe_display_filename(os.path.basename(filename))
    if is_unsafe_filename(safe_name):
        flash('Invalid filename', 'error')
        return redirect(url_for('index'))
    zip_path = secure_path(os.path.join(app.config['OUTPUT_FOLDER'], safe_name))
    if not zip_path or not os.path.exists(zip_path):
        flash('File not found', 'error')
        return redirect(url_for('index'))
    return send_file(zip_path, as_attachment=True)


@app.route('/download/<filename>')
def download(filename):
    """Serve a single file for download."""
    safe_name = safe_display_filename(os.path.basename(filename))
    if is_unsafe_filename(safe_name):
        flash('Invalid filename', 'error')
        return redirect(url_for('index'))
    filepath = secure_path(os.path.join(app.config['OUTPUT_FOLDER'], safe_name))
    if not filepath or not os.path.exists(filepath):
        flash('File not found', 'error')
        return redirect(url_for('index'))
    with open(filepath, 'rb') as f:
        response = Response(f.read(), mimetype='application/octet-stream')
        response.headers['Content-Disposition'] = f'attachment; filename="{safe_name}"'
    return response


_preview_cache = {}
_preview_cache_lock = threading.Lock()


def build_preview_thumbnail(filepath, width):
    """Downscale an uploaded frame for the GIF-creation preview, returning
    (bytes, mimetype) or None if the format can't be read here.

    Uses PIL rather than ImageMagick: the preview only runs on formats the GIF
    creation flow already accepts, and JPEG draft mode lets libjpeg decode a
    12 MP frame straight to roughly preview size, which is what keeps a
    full-resolution sequence from taking seconds per frame to load.
    """
    try:
        stat = os.stat(filepath)
    except OSError:
        return None
    key = (filepath, stat.st_mtime_ns, stat.st_size, width)

    with _preview_cache_lock:
        cached = _preview_cache.get(key)
    if cached:
        return cached

    try:
        with Image.open(filepath) as img:
            img.draft('RGB', (width, width))  # JPEG fast path; a no-op elsewhere
            img.load()
            # Matches the -auto-orient the real pipeline applies, so the preview
            # isn't sideways for frames that the finished animation gets right.
            img = ImageOps.exif_transpose(img)
            has_alpha = 'A' in img.getbands() or 'transparency' in img.info
            img = img.convert('RGBA' if has_alpha else 'RGB')
            img.thumbnail((width, width * 4), Image.LANCZOS)
            buffer = io.BytesIO()
            if has_alpha:
                img.save(buffer, 'PNG', optimize=True)
                mimetype = 'image/png'
            else:
                img.save(buffer, 'JPEG', quality=82, progressive=True)
                mimetype = 'image/jpeg'
    except Exception as e:
        app.logger.info(f"Preview thumbnail unavailable for {os.path.basename(filepath)}: {e}")
        return None

    result = (buffer.getvalue(), mimetype)
    with _preview_cache_lock:
        if len(_preview_cache) >= PREVIEW_CACHE_MAX_ENTRIES:
            _preview_cache.pop(next(iter(_preview_cache)), None)
        _preview_cache[key] = result
    return result


@app.route('/preview_frame/<filename>')
def preview_frame(filename):
    """Serve an already-uploaded (not yet processed) image back to the browser,
    for the client-side GIF-creation timing preview only. Read-only, same
    path-confinement as download() but rendered inline instead of downloaded.
    With ?w=<px> a downscaled copy is returned, which is what the preview asks
    for; the original is only served as a fallback. Plain 404 on failure since
    this is only ever hit as an <img src> target, not a user-facing navigation."""
    safe_name = os.path.basename(filename)
    if is_unsafe_filename(safe_name):
        return ('', 404)
    filepath = secure_path(os.path.join(app.config['UPLOAD_FOLDER'], safe_name))
    if not filepath or not os.path.exists(filepath):
        return ('', 404)

    width = request.args.get('w', type=int)
    if width:
        thumbnail = build_preview_thumbnail(filepath, max(120, min(PREVIEW_MAX_WIDTH, width)))
        if thumbnail:
            data, mimetype = thumbnail
            response = Response(data, mimetype=mimetype)
            response.headers['Cache-Control'] = 'private, max-age=3600'
            return response

    return send_file(filepath)


def is_safe_url(url):
    """Validate URL safety: scheme, extension, and resolved-IP range checks.

    Resolves the hostname via DNS and rejects any address that falls within
    loopback, link-local, private, multicast, or otherwise reserved ranges.
    This prevents SSRF attacks including DNS-rebinding and cloud-metadata
    endpoint abuse (169.254.169.254, etc.).
    """
    try:
        ALLOWED_SCHEMES = {'http', 'https'}

        parsed = urlparse(url)

        if parsed.scheme.lower() not in ALLOWED_SCHEMES:
            return False

        hostname = parsed.hostname
        if not hostname:
            return False

        path = parsed.path.lower()
        if not any(path.endswith(ext) for ext in URL_IMPORT_EXTENSIONS):
            return False

        # Resolve all DNS addresses and reject any private/reserved IP.
        try:
            addr_infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
        except socket.gaierror:
            return False

        if not addr_infos:
            return False

        for addr_info in addr_infos:
            ip_str = addr_info[4][0]
            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError:
                return False
            if (ip.is_loopback or ip.is_link_local or ip.is_multicast
                    or ip.is_reserved or ip.is_unspecified or ip.is_private):
                return False

        return True
    except Exception:
        return False


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)