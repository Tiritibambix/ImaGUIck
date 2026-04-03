from flask import Flask, render_template, request, redirect, url_for, send_file, flash, Response
import os
import subprocess
import uuid
import threading
import json
import time
from zipfile import ZipFile
from datetime import datetime
from werkzeug.utils import secure_filename
from PIL import Image
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
DEFAULTS = {
    "quality": "100",
    "width": "",
    "height": "",
    "percentage": "",
}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE
app.config['UPLOAD_EXTENSIONS'] = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.tiff', '.bmp', '.arw', '.jxl']
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev-insecure-key-change-in-prod')
app.logger.setLevel(logging.INFO)

# --- Async batch processing state ---
jobs = {}
jobs_lock = threading.Lock()
_processing_semaphore = threading.BoundedSemaphore(4)
executor = ThreadPoolExecutor(max_workers=16)

# Server-side upload sessions: maps a short key -> list of saved filenames.
# Avoids embedding long filename lists in redirect URLs (Gunicorn 4094-char limit).
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
    """Allow all image file types supported by ImageMagick, but block potentially dangerous extensions."""
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
        re.match(r'^imaguick_[a-f0-9]{32}\.png$', basename) is not None
    )


def prepare_input_file(filepath):
    """If the file is JXL, decode it to a unique temp PNG for ImageMagick.
    Returns (input_path, tmp_path). tmp_path is None if no temp was created.
    Caller is responsible for deleting tmp_path (use try/finally)."""
    if filepath.lower().endswith('.jxl'):
        validated = secure_path(filepath)
        if not validated:
            raise ValueError(f"Insecure JXL path: {filepath}")
        tmp_path = f'/tmp/imaguick_{uuid.uuid4().hex}.png'
        subprocess.run(['djxl', '--', validated, tmp_path], check=True, timeout=60)
        return tmp_path, tmp_path
    return filepath, None


def get_image_dimensions(filepath):
    """Get image dimensions using appropriate tool based on file type."""
    try:
        secure_file_path = secure_path(filepath)
        if not secure_file_path:
            raise Exception("Invalid file path")

        if filepath.lower().endswith('.arw'):
            app.logger.info(f"Getting dimensions for ARW file: {filepath}")
            cmd = ['exiftool', '-s', '-s', '-s', '-PreviewImageLength', '-PreviewImageWidth', secure_file_path]
            app.logger.info(f"Running exiftool command")
            result = subprocess.run(cmd, capture_output=True, text=True, shell=False, timeout=30)

            if result.returncode == 0 and result.stdout.strip():
                app.logger.info(f"Exiftool output received")
                dimensions = result.stdout.strip().split('\n')
                if len(dimensions) == 2:
                    try:
                        height = int(dimensions[0])
                        width = int(dimensions[1])
                        if not (0 < width < MAX_DIMENSION and 0 < height < MAX_DIMENSION):
                            raise ValueError(f"Image dimensions ({width}x{height}) exceed maximum allowed ({MAX_DIMENSION}px)")
                        app.logger.info(f"Successfully parsed dimensions: {width}x{height}")
                        return width, height
                    except ValueError:
                        app.logger.warning("Could not parse dimensions from exiftool output")
                        pass

            return 7008, 4672
        else:
            app.logger.info(f"Getting dimensions for non-ARW file")
            cmd = ['magick', 'identify', secure_file_path]
            app.logger.info(f"Running ImageMagick command")
            result = subprocess.run(cmd, capture_output=True, text=True, shell=False, timeout=30)
            if result.returncode != 0:
                raise Exception(f"Error getting image dimensions: {result.stderr}")

            match = re.search(r'\s(\d+)x(\d+)\s', result.stdout)
            if match:
                width = int(match.group(1))
                height = int(match.group(2))
                if not (0 < width < MAX_DIMENSION and 0 < height < MAX_DIMENSION):
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
            'name': 'Animation & Video',
            'formats': ['GIF', 'APNG', 'MNG', 'WEBP', 'JIF', 'MP4']
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

    # PNG est toujours recommandé car c'est un excellent format sans perte
    recommended.add('PNG')

    if image_type.get('has_transparency'):
        recommended.update(['WEBP', 'AVIF'])

    if image_type.get('is_photo'):
        recommended.update(['JPEG', 'WEBP', 'AVIF', 'HEIC', 'DNG', 'JXL'])
    else:
        # Pour les graphiques, logos, etc.
        recommended.update(['WEBP', 'SVG', 'JXL'])

    # Cas spéciaux basés sur le format original
    if original_format:
        original_format = original_format.upper()
        if original_format in ['ARW', 'CR2', 'CR3', 'NEF', 'RAF', 'RW2', 'DNG']:
            recommended.update(['TIFF', 'DNG'])
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


def get_available_formats(filepath=None):
    """Get all formats supported by ImageMagick and organize them by category."""
    try:
        VIDEO_FORMATS = {'3G2', '3GP', 'AVI', 'FLV', 'M4V', 'MKV', 'MOV', 'MP4', 'MPG', 'MPEG', 'OGV', 'SWF', 'VOB', 'WMV'}

        result = subprocess.run(['magick', '-list', 'format'], capture_output=True, text=True)

        if result.returncode != 0:
            raise Exception("Failed to retrieve format list from ImageMagick")

        available_formats = set()
        for line in result.stdout.split('\n'):
            if not line.strip() or line.startswith('Format') or line.startswith('--'):
                continue

            parts = line.split()
            if len(parts) >= 2:
                format_name = parts[0].strip('* ')
                format_flags = parts[1].lower()
                if 'r' in format_flags or 'w' in format_flags:
                    if format_name.upper() not in VIDEO_FORMATS:
                        available_formats.add(format_name.upper())

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


def _analyze_with_pil(filepath):
    """Analyze image with PIL and return type dict."""
    with Image.open(filepath) as img:
        has_transparency = 'A' in img.getbands()
        is_photo = True
        if img.mode in ('P', '1', 'L'):
            is_photo = False
        elif img.mode in ('RGB', 'RGBA'):
            pixels = list(img.getdata())
            unique_colors = len(set(pixels[:1000]))
            is_photo = unique_colors > 100
        return {
            'has_transparency': has_transparency,
            'is_photo': is_photo,
            'original_format': img.format
        }


def analyze_image_type(filepath):
    """Analyze image to determine its type and best suitable formats."""
    try:
        validated_path = secure_path(filepath)
        if not validated_path or not os.path.exists(validated_path):
            raise ValueError("File does not exist or is not in an allowed directory.")

        if validated_path.lower().endswith('.arw'):
            app.logger.info(f"Analyzing RAW file: {validated_path}")
            return {'has_transparency': False, 'is_photo': True, 'original_format': 'ARW'}

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
        return {'has_transparency': False, 'is_photo': True, 'original_format': None}


def flash_error(message):
    """Flash error message and log if needed."""
    app.logger.error(message)
    flash(message)
    return render_template('result.html',
                           success=False,
                           title='Error',
                           return_url=request.referrer)


def extract_processing_params(form):
    """Extract all image processing parameters from a form."""
    return {
        'width': form.get('width', DEFAULTS['width']),
        'height': form.get('height', DEFAULTS['height']),
        'percentage': form.get('percentage', DEFAULTS['percentage']),
        'quality': form.get('quality', DEFAULTS['quality']),
        'keep_ratio': 'keep_ratio' in form,
        'output_format': form.get('format', '').upper(),
        'auto_level': form.get('auto_level') == 'on',
        'auto_gamma': form.get('auto_gamma') == 'on',
        'use_1080p': form.get('use_1080p') == 'on',
        'use_1920p': form.get('use_1920p') == 'on',
        'use_sharpen': form.get('use_sharpen') == 'on',
        'sharpen_level': form.get('sharpen_level', 'standard'),
    }


def build_imagemagick_command(filepath, output_path, width, height, percentage, quality, keep_ratio,
                              auto_level=False, auto_gamma=False, use_1080p=False, use_1920p=False,
                              use_sharpen=False, sharpen_level='standard'):
    """Build ImageMagick command for resizing and formatting.
    filepath must already be decoded (JXL → PNG via prepare_input_file before calling this)."""
    if not (secure_path(filepath) or is_valid_tmp_path(filepath)):
        app.logger.error("Insecure input file path detected")
        return None
    if not secure_path(output_path):
        app.logger.error("Insecure output path detected")
        return None

    command = ['magick', filepath]

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
                resize_value = f"{float(percentage)}%"
                command.extend(['-resize', resize_value])
            except ValueError:
                return None
        elif width or height:
            try:
                if width:
                    width = int(width)
                if height:
                    height = int(height)

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

    if quality and quality != "100":
        try:
            quality_value = int(quality)
            if 1 <= quality_value <= 100:
                command.extend(['-quality', str(quality_value)])
        except ValueError:
            return None

    command.append(output_path)
    return command


# --- Async batch processing functions ---

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

            input_path, tmp_path = prepare_input_file(filepath)
            try:
                command = build_imagemagick_command(
                    filepath=input_path,
                    output_path=output_path,
                    width=params['width'],
                    height=params['height'],
                    percentage=params['percentage'],
                    quality=params['quality'],
                    keep_ratio=params['keep_ratio'],
                    auto_level=params['auto_level'],
                    auto_gamma=params['auto_gamma'],
                    use_1080p=params['use_1080p'],
                    use_1920p=params['use_1920p'],
                    use_sharpen=params['use_sharpen'],
                    sharpen_level=params['sharpen_level'],
                )
                if not command:
                    raise RuntimeError(f"Could not build ImageMagick command for {fname}")

                app.logger.info(f"[Job {job_id}] Executing: {' '.join(command)}")
                subprocess.run(command, check=True, capture_output=True, text=True, timeout=300)
            except subprocess.CalledProcessError as e:
                app.logger.error(f"[Job {job_id}] ImageMagick error for {fname}: {e.stderr}")
                raise RuntimeError(f"Image processing failed for {fname}")
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    os.remove(tmp_path)

            # Clean up source file after successful processing
            try:
                src = secure_path(filepath)
                if src and os.path.exists(src):
                    os.remove(src)
            except Exception:
                pass

            with jobs_lock:
                file_info['status'] = 'done'
                file_info['output'] = output_path
                jobs[job_id]['done'] += 1

        except Exception as e:
            app.logger.error(f"[Job {job_id}] Error processing {fname}: {e}")
            with jobs_lock:
                file_info['status'] = 'error'
                file_info['error'] = 'Processing error'
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
    """Handle file uploads. Supports both regular form POST and XHR (returns JSON)."""
    is_xhr = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

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
            errors.append(f"Format non supporté : {secure_filename(file.filename)}")
            continue
        unique_name = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
        file.save(filepath)
        # Per-file size check after saving
        if os.path.getsize(filepath) > PER_FILE_MAX_SIZE:
            os.remove(filepath)
            errors.append(
                f"{secure_filename(file.filename)} exceeds the per-file limit of "
                f"{PER_FILE_MAX_SIZE // 1024 // 1024} MB"
            )
            continue
        uploaded_files.append(unique_name)

    for err in errors:
        flash(err, 'error')

    if not uploaded_files:
        msg = errors[0] if errors else 'No valid file'
        return _error(msg)

    if len(uploaded_files) == 1:
        redirect_url = url_for('resize_options', filename=uploaded_files[0])
    else:
        # Store filenames server-side to avoid URL length limit (Gunicorn 4094 chars)
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

        filename = secure_filename(os.path.basename(url.split('?')[0]))
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
    sanitized_filename = secure_filename(os.path.basename(filename))
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], sanitized_filename)
    if not os.path.exists(filepath):
        flash_error("File not found.")
        return redirect(url_for('index'))

    dimensions = get_image_dimensions(filepath)
    if not dimensions or dimensions == (None, None):
        flash('Image too large or unsupported (max 10000px per side)', 'error')
        return redirect(url_for('index'))

    formats = get_available_formats(filepath)

    app.logger.info(f"Formats passed to template: {formats}")
    return render_template('resize.html',
                           filename=sanitized_filename,
                           width=dimensions[0],
                           height=dimensions[1],
                           formats=formats,
                           defaults=DEFAULTS)


@app.route('/resize/<filename>', methods=['POST'])
def resize_image(filename):
    """Handle resizing or format conversion for a single image."""
    filename = os.path.basename(filename)
    if not re.match(r'^[\w\-.]+$', filename) or '..' in filename or filename.startswith('/'):
        flash('Invalid filename')
        return render_template('result.html',
                               success=False,
                               title='Error',
                               return_url=url_for('index'))
    try:
        width = request.form.get('width', '')
        height = request.form.get('height', '')
        keep_ratio = request.form.get('keep_ratio') == 'on'
        output_format = request.form.get('format', '').upper()
        auto_level = request.form.get('auto_level') == 'on'
        auto_gamma = request.form.get('auto_gamma') == 'on'
        use_sharpen = request.form.get('use_sharpen') == 'on'
        sharpen_level = request.form.get('sharpen_level', 'standard')

        app.logger.info(f"Processing resize request for {filename}")
        app.logger.info(f"Sharpening: enabled={use_sharpen}, level={sharpen_level}")
        app.logger.info(f"Initial parameters: width={width}, height={height}, keep_ratio={keep_ratio}")

        if keep_ratio and (width.isdigit() or height.isdigit()):
            filepath = secure_path(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            original_dimensions = get_image_dimensions(filepath) if filepath else None
            if original_dimensions:
                original_width, original_height = original_dimensions
                if width.isdigit() and not height.isdigit():
                    new_width = int(width)
                    height = str(round(new_width * original_height / original_width))
                    app.logger.info(f"Calculated proportional height: {height}")
                elif height.isdigit() and not width.isdigit():
                    new_height = int(height)
                    width = str(round(new_height * original_width / original_height))
                    app.logger.info(f"Calculated proportional width: {width}")

        app.logger.info(f"Final parameters: width={width}, height={height}, format={output_format}")

        filepath = secure_path(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        if not filepath or not os.path.exists(filepath):
            flash('File not found')
            return render_template('result.html',
                                   success=False,
                                   title='Error',
                                   return_url=url_for('resize_options', filename=filename))

        # Strip UUID prefix (32 hex chars + underscore) to restore original filename
        clean_name = re.sub(r'^[a-f0-9]{32}_', '', filename)
        base_name = os.path.splitext(clean_name)[0]
        if output_format:
            output_filename = f"{base_name}_imaGUIck.{output_format.lower()}"
        else:
            output_filename = f"{base_name}_imaGUIck{os.path.splitext(clean_name)[1]}"

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
                sharpen_level=sharpen_level
            )

            if not command:
                flash('Error preparing resize command')
                return render_template('result.html',
                                       success=False,
                                       title='Error',
                                       return_url=url_for('resize_options', filename=filename))

            app.logger.info(f"Executing command: {' '.join(command)}")
            subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            app.logger.error(f"ImageMagick error for {filename}: {e.stderr}")
            flash('An error occurred while processing the image.')
            return render_template('result.html',
                                   success=False,
                                   title='Error',
                                   return_url=url_for('resize_options', filename=filename))
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

        flash('Image processed successfully!')
        return render_template('result.html',
                               success=True,
                               title='Success',
                               filename=output_filename,
                               batch=False)

    except Exception as e:
        app.logger.error(f"Error during resize: {str(e)}")
        flash('An error occurred during processing.')
        return render_template('result.html',
                               success=False,
                               title='Error',
                               return_url=url_for('resize_options', filename=filename))


@app.route('/resize_batch_options')
def resize_batch_options(filenames=None):
    """Resize options page for batch processing."""
    if not filenames:
        upload_key = request.args.get('upload_key')
        if upload_key:
            with upload_sessions_lock:
                filenames = upload_sessions.get(upload_key, [])
        else:
            # Legacy fallback: filenames in query string
            filenames = [f for f in request.args.get('filenames', '').split(',') if f]

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
        fpath = secure_path(os.path.join(app.config['UPLOAD_FOLDER'], os.path.basename(fname)))
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

    job_id = uuid.uuid4().hex
    with jobs_lock:
        jobs[job_id] = {
            'files': file_list,
            'params': params,
            'batch_folder': batch_folder,
            'timestamp': timestamp,
            'zip': None,
            'total': len(file_list),
            'done': 0,
            'errors': 0,
            'status': 'processing'
        }

    t = threading.Thread(target=process_job, args=(job_id,), daemon=True)
    t.start()

    return redirect(url_for('job_progress', job_id=job_id))


@app.route('/job/<job_id>/progress')
def job_progress(job_id):
    """Progress page for a batch job."""
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        flash('Job not found', 'error')
        return redirect(url_for('index'))
    return render_template('progress.html', job_id=job_id, total=job['total'])


@app.route('/job/<job_id>/status')
def job_status(job_id):
    """SSE endpoint streaming real-time job status."""
    def generate():
        while True:
            with jobs_lock:
                job = jobs.get(job_id)
                if not job:
                    yield 'data: {"error": "job not found"}\n\n'
                    return
                payload = {
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
    safe_name = os.path.basename(filename)
    if not re.match(r'^[\w\-.]+$', safe_name) or '..' in safe_name:
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
    safe_name = os.path.basename(filename)
    if not re.match(r'^[\w\-.]+$', safe_name) or '..' in safe_name:
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


def is_safe_url(url):
    """Validate URL safety: scheme, extension, and resolved-IP range checks.

    Resolves the hostname via DNS and rejects any address that falls within
    loopback, link-local, private, multicast, or otherwise reserved ranges.
    This prevents SSRF attacks including DNS-rebinding and cloud-metadata
    endpoint abuse (169.254.169.254, etc.).
    """
    try:
        ALLOWED_SCHEMES = {'http', 'https'}
        ALLOWED_EXTENSIONS = {
            '.jpg', '.jpeg', '.png', '.gif', '.webp', '.tiff', '.bmp',
            '.avif', '.heic', '.jxl', '.arw', '.cr2', '.cr3', '.nef',
            '.raf', '.rw2', '.dng', '.svg', '.pdf', '.eps', '.apng',
        }

        parsed = urlparse(url)

        if parsed.scheme.lower() not in ALLOWED_SCHEMES:
            return False

        hostname = parsed.hostname
        if not hostname:
            return False

        path = parsed.path.lower()
        if not any(path.endswith(ext) for ext in ALLOWED_EXTENSIONS):
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
