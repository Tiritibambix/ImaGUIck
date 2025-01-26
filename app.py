from flask import Flask, render_template, request, redirect, url_for, send_file, flash, Response
import os
import subprocess
from zipfile import ZipFile
from datetime import datetime
from werkzeug.utils import secure_filename
from PIL import Image
import requests
import logging
import re

# Configuration
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'output'
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff', 'webp', 'arw', 'cr2', 'nef'}
ALLOWED_URL_SCHEMES = {'http', 'https'}
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB max
DEFAULTS = {
    "quality": "100",
    "width": "",
    "height": "",
    "percentage": "",
}

# Ensure paths are absolute and secure
UPLOAD_FOLDER = os.path.abspath(UPLOAD_FOLDER)
OUTPUT_FOLDER = os.path.abspath(OUTPUT_FOLDER)

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'supersecretkey')  # Better to use env variable
app.logger.setLevel(logging.INFO)

def is_safe_path(basedir, path):
    """Ensure the path is contained within the base directory"""
    try:
        return os.path.abspath(path).startswith(os.path.abspath(basedir))
    except (TypeError, ValueError):
        return False

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def sanitize_filename(filename):
    """Sanitize filename to prevent path traversal"""
    return secure_filename(filename)

def validate_url(url):
    """Validate URL scheme and domain"""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.scheme in ALLOWED_URL_SCHEMES
    except:
        return False

def secure_command(cmd_list):
    """Validate and sanitize command arguments"""
    # Ensure all arguments are strings and don't contain shell metacharacters
    sanitized = []
    for arg in cmd_list:
        if not isinstance(arg, str):
            arg = str(arg)
        # Remove any shell metacharacters
        arg = re.sub(r'[;&|`$]', '', arg)
        sanitized.append(arg)
    return sanitized

def get_image_dimensions(filepath):
    """Get image dimensions using appropriate tool based on file type."""
    try:
        if not is_safe_path(app.config['UPLOAD_FOLDER'], filepath):
            raise ValueError("Invalid file path")

        if filepath.lower().endswith('.arw'):
            app.logger.info(f"Getting dimensions for ARW file: {filepath}")
            cmd = secure_command(['exiftool', '-s', '-s', '-s', '-PreviewImageLength', '-PreviewImageWidth', filepath])
            result = subprocess.run(cmd, capture_output=True, text=True, shell=False)
            
            if result.returncode == 0 and result.stdout.strip():
                app.logger.info(f"Exiftool output: {result.stdout}")
                dimensions = result.stdout.strip().split('\n')
                if len(dimensions) == 2:
                    try:
                        height = int(dimensions[0])
                        width = int(dimensions[1])
                        return width, height
                    except ValueError:
                        app.logger.warning("Could not parse dimensions from exiftool output")
            return 7008, 4672  # Fallback dimensions for Sony A7 IV
        else:
            app.logger.info(f"Getting dimensions for non-ARW file: {filepath}")
            cmd = secure_command(['magick', 'identify', filepath])
            result = subprocess.run(cmd, capture_output=True, text=True, shell=False)
            if result.returncode != 0:
                raise Exception(f"Error getting image dimensions: {result.stderr}")
            
            match = re.search(r'\s(\d+)x(\d+)\s', result.stdout)
            if match:
                width = int(match.group(1))
                height = int(match.group(2))
                return width, height
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
            'formats': ['WEBP', 'AVIF', 'JPEG', 'JPG', 'PNG', 'GIF']
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
    
    if image_type.get('has_transparency'):
        recommended.update(['PNG', 'WEBP', 'AVIF'])
    
    if image_type.get('is_photo'):
        recommended.update(['JPEG', 'WEBP', 'AVIF', 'HEIC'])
    else:
        # Pour les graphiques, logos, etc.
        recommended.update(['PNG', 'WEBP', 'SVG'])
    
    # Cas spéciaux basés sur le format original
    if original_format:
        original_format = original_format.upper()
        if original_format in ['GIF', 'WEBP', 'MNG', 'APNG']:
            # Format d'animation
            recommended.update(['GIF', 'WEBP', 'APNG'])
        elif original_format in ['ICO', 'CUR', 'ICON']:
            # Format d'icône
            recommended.update(['ICO', 'PNG'])
        elif original_format in ['SVG', 'EPS', 'AI', 'PDF']:
            # Format vectoriel
            recommended.update(['SVG', 'PDF', 'EPS', 'PNG'])
        elif original_format in ['PSD', 'XCF', 'PSB']:
            # Format d'édition
            recommended.update(['PSD', 'TIFF', 'PNG'])
    
    return sorted(list(recommended))

def get_available_formats(filepath=None):
    """Get all formats supported by ImageMagick and organize them by category."""
    try:
        # Liste des formats vidéo à exclure
        VIDEO_FORMATS = {'3G2', '3GP', 'AVI', 'FLV', 'M4V', 'MKV', 'MOV', 'MP4', 'MPG', 'MPEG', 'OGV', 'SWF', 'VOB', 'WMV'}
        
        # Obtenir la liste des formats depuis ImageMagick
        result = subprocess.run(['magick', '-list', 'format'], capture_output=True, text=True)
        
        if result.returncode != 0:
            raise Exception("Erreur lors de la récupération des formats")
            
        # Parser la sortie pour extraire les formats
        available_formats = set()
        for line in result.stdout.split('\n'):
            if not line.strip() or line.startswith('Format') or line.startswith('--'):
                continue
                
            parts = line.split()
            if len(parts) >= 2:
                format_name = parts[0].strip('* ')
                format_flags = parts[1].lower()
                if 'r' in format_flags or 'w' in format_flags:
                    if format_name.upper() not in VIDEO_FORMATS:  # Exclure les formats vidéo
                        available_formats.add(format_name.upper())
        
        if not available_formats:
            raise Exception("Aucun format n'a été trouvé dans la sortie de ImageMagick")
            
        app.logger.info(f"Formats détectés : {available_formats}")
        
        # Organiser les formats disponibles par catégorie
        categories = get_format_categories()
        categorized_formats = {}
        
        # Créer un ensemble de tous les formats catégorisés
        all_categorized = set()
        for cat_info in categories.values():
            all_categorized.update(cat_info['formats'])
            
        # Ajouter les catégories dans l'ordre spécifié
        ordered_categories = ['recommended', 'photo', 'web', 'icons', 'animation', 'graphics', 'archive', 'other']
        
        # Si un fichier est spécifié, ajouter les formats recommandés
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
                continue  # Déjà ajouté si présent
            elif cat_key == 'other':
                # Traiter les formats non catégorisés
                uncategorized = sorted(list(available_formats - all_categorized))
                if uncategorized:
                    categorized_formats['other'] = {
                        'name': 'Other Available Formats',
                        'formats': uncategorized
                    }
            elif cat_key in categories:
                # Traiter les catégories prédéfinies
                matching_formats = sorted(list(available_formats.intersection(categories[cat_key]['formats'])))
                if matching_formats:
                    categorized_formats[cat_key] = {
                        'name': categories[cat_key]['name'],
                        'formats': matching_formats
                    }
            
        return categorized_formats
        
    except Exception as e:
        app.logger.error(f"Erreur lors de la récupération des formats : {e}")
        # En cas d'erreur, retourner au moins la catégorie "Other" avec des formats de base
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

def analyze_image_type(filepath):
    """Analyze image to determine its type and best suitable formats."""
    try:
        # Vérifier si c'est un fichier RAW
        if filepath.lower().endswith('.arw'):
            app.logger.info(f"Analyzing RAW file: {filepath}")
            return {
                'has_transparency': False,
                'is_photo': True,
                'original_format': 'ARW'
            }
            
        # Pour les autres formats, utiliser PIL
        with Image.open(filepath) as img:
            has_transparency = 'A' in img.getbands()
            is_photo = True
            
            # Check if image is more like a photo or graphic
            if img.mode in ('P', '1', 'L'):
                is_photo = False
            elif img.mode in ('RGB', 'RGBA'):
                # Sample pixels to determine if it's likely a photo
                pixels = list(img.getdata())
                unique_colors = len(set(pixels[:1000]))  # Sample first 1000 pixels
                is_photo = unique_colors > 100  # If many unique colors, likely a photo
            
            return {
                'has_transparency': has_transparency,
                'is_photo': is_photo,
                'original_format': img.format
            }
    except Exception as e:
        app.logger.error(f"Error analyzing image: {e}")
        # En cas d'erreur, supposer que c'est une photo sans transparence
        return {
            'has_transparency': False,
            'is_photo': True,
            'original_format': None
        }

def flash_error(message):
    """Flash error message and log if needed."""
    flash(message)
    app.logger.error(message)

def build_imagemagick_command(filepath, output_path, width, height, percentage, quality, keep_ratio):
    """Build ImageMagick command for resizing and formatting."""
    if not is_safe_path(app.config['UPLOAD_FOLDER'], filepath) or \
       not is_safe_path(app.config['OUTPUT_FOLDER'], output_path):
        raise ValueError("Invalid file path")

    cmd = ['magick', 'convert']
    
    # Validate numeric inputs
    try:
        if width:
            width = int(width)
            if width <= 0 or width > 20000:
                raise ValueError("Invalid width")
        if height:
            height = int(height)
            if height <= 0 or height > 20000:
                raise ValueError("Invalid height")
        if percentage:
            percentage = float(percentage)
            if percentage <= 0 or percentage > 1000:
                raise ValueError("Invalid percentage")
        if quality:
            quality = int(quality)
            if quality < 1 or quality > 100:
                raise ValueError("Invalid quality")
    except ValueError as e:
        raise ValueError(f"Invalid parameter: {str(e)}")

    # Add input file
    cmd.append(filepath)

    # Add resize options
    resize_opts = []
    if width or height:
        resize_opts.append(f"{width or ''}x{height or ''}")
        if not keep_ratio:
            resize_opts.append("!")
    elif percentage:
        resize_opts.append(f"{percentage}%")
    
    if resize_opts:
        cmd.extend(['-resize', ''.join(resize_opts)])

    # Add quality
    if quality:
        cmd.extend(['-quality', str(quality)])

    # Add output file
    cmd.append(output_path)

    return secure_command(cmd)

@app.route('/')
def index():
    """Homepage with upload options."""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file uploads."""
    if 'file' not in request.files:
        flash('Aucun fichier sélectionné', 'error')
        return redirect(url_for('index'))
        
    files = request.files.getlist('file')
    if not files or all(file.filename == '' for file in files):
        flash('Veuillez sélectionner au moins un fichier', 'error')
        return redirect(url_for('index'))
        
    uploaded_files = []
    for file in files:
        if file and allowed_file(file.filename):
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(file.filename))
            file.save(filepath)
            uploaded_files.append(filepath)
        else:
            flash_error(f"Unsupported file format for {file.filename}.")

    if len(uploaded_files) == 1:
        return redirect(url_for('resize_options', filename=os.path.basename(uploaded_files[0])))
    if len(uploaded_files) > 1:
        return redirect(url_for('resize_batch_options', filenames=','.join(map(os.path.basename, uploaded_files))))
    return redirect(url_for('index'))

@app.route('/upload_url', methods=['POST'])
def upload_url():
    """Handle image upload from a URL."""
    try:
        url = request.form.get('url')
        if not url or not validate_url(url):
            flash("URL invalide ou non autorisée", "error")
            return redirect(url_for('index'))

        response = requests.get(url, stream=True, timeout=10, verify=True)
        response.raise_for_status()

        content_type = response.headers.get('content-type', '').lower()
        if not content_type.startswith('image/'):
            flash("Le fichier n'est pas une image valide", "error")
            return redirect(url_for('index'))

        # Get filename from URL or generate one
        filename = sanitize_filename(os.path.basename(url)) or 'image.jpg'
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        # Save file securely
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        return redirect(url_for('resize_options', filename=filename))
    except Exception as e:
        app.logger.error(f"Error downloading image: {str(e)}")
        flash("Erreur lors du téléchargement de l'image", "error")
        return redirect(url_for('index'))

@app.route('/resize_options/<filename>')
def resize_options(filename):
    """Resize options page for a single image."""
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    dimensions = get_image_dimensions(filepath)
    if not dimensions:
        return redirect(url_for('index'))

    # Récupérer les formats disponibles déjà catégorisés
    formats = get_available_formats(filepath)

    return render_template('resize.html',
                         filename=filename,
                         width=dimensions[0],
                         height=dimensions[1],
                         formats=formats,
                         defaults=DEFAULTS)

@app.route('/resize/<filename>', methods=['POST'])
def resize_image(filename):
    """Handle resizing or format conversion for a single image."""
    try:
        # Récupérer les paramètres
        width = request.form.get('width', '')
        height = request.form.get('height', '')
        keep_ratio = request.form.get('keep_ratio') == 'on'
        output_format = request.form.get('format', '').upper()
        
        app.logger.info(f"Processing resize request for {filename}")
        app.logger.info(f"Initial parameters: width={width}, height={height}, keep_ratio={keep_ratio}")
        
        # Si keep_ratio est True et une seule dimension est fournie, calculer l'autre
        if keep_ratio and (width.isdigit() or height.isdigit()):
            # Obtenir les dimensions originales
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            original_dimensions = get_image_dimensions(filepath)
            if original_dimensions:
                original_width, original_height = original_dimensions
                if width.isdigit() and not height.isdigit():
                    # Calculer la hauteur proportionnelle
                    new_width = int(width)
                    height = str(round(new_width * original_height / original_width))
                    app.logger.info(f"Calculated proportional height: {height}")
                elif height.isdigit() and not width.isdigit():
                    # Calculer la largeur proportionnelle
                    new_height = int(height)
                    width = str(round(new_height * original_width / original_height))
                    app.logger.info(f"Calculated proportional width: {width}")
        
        app.logger.info(f"Final parameters: width={width}, height={height}, format={output_format}")
        
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if not os.path.exists(filepath):
            flash('File not found')
            return redirect(url_for('index'))
            
        # Créer un nom de fichier pour la sortie
        base_name = os.path.splitext(filename)[0]
        if output_format:
            output_filename = f"{base_name}_resized.{output_format.lower()}"
        else:
            output_filename = f"{base_name}_resized{os.path.splitext(filename)[1]}"
            
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)
        app.logger.info(f"Output path: {output_path}")
        
        # Préparer et exécuter les commandes
        error, commands, temp_file = build_imagemagick_command(
            filepath=filepath,
            output_path=output_path,
            width=width,
            height=height,
            percentage=request.form.get('percentage', DEFAULTS["percentage"]),
            quality=request.form.get('quality', DEFAULTS["quality"]),
            keep_ratio=keep_ratio
        )
        
        if error:
            flash(error)
            return redirect(url_for('resize_options', filename=filename))
            
        if not commands:
            flash('Error preparing resize command')
            return redirect(url_for('resize_options', filename=filename))
            
        # Exécuter les commandes en séquence
        for cmd in commands:
            app.logger.info(f"Running command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                app.logger.error(f"Command failed: {result.stderr}")
                flash(f'Error during image processing: {result.stderr}')
                return redirect(url_for('resize_options', filename=filename))
                
        # Nettoyer les fichiers temporaires
        try:
            if temp_file and os.path.exists(temp_file):
                os.remove(temp_file)
            temp_resized = os.path.join(os.path.dirname(output_path), "temp_resized.png")
            if os.path.exists(temp_resized):
                os.remove(temp_resized)
        except Exception as e:
            app.logger.warning(f"Error cleaning temporary files: {e}")
            
        # Forcer le téléchargement du fichier
        return send_file(
            output_path,
            as_attachment=True,
            download_name=output_filename,
            mimetype=f'image/{output_format.lower() if output_format else os.path.splitext(filename)[1][1:].lower()}'
        )
        
    except Exception as e:
        app.logger.error(f"Error during resize: {e}")
        flash(f'Error during resize: {str(e)}')
        return redirect(url_for('resize_options', filename=filename))

@app.route('/resize_batch_options')
def resize_batch_options(filenames=None):
    """Resize options page for batch processing."""
    if not filenames:
        filenames = request.args.get('filenames', '').split(',')
    
    if not filenames or not filenames[0]:
        return redirect(url_for('index'))

    # Analyze all images in the batch
    batch_info = {
        'has_transparency': False,
        'has_photos': False,
        'has_graphics': False,
        'total_files': len(filenames)
    }

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

    # Récupérer les formats disponibles basés sur le premier fichier
    formats = get_available_formats(first_file_path)

    return render_template('resize_batch.html',
                         files=filenames,
                         formats=formats,
                         batch_info=batch_info,
                         defaults=DEFAULTS)

@app.route('/resize_batch', methods=['POST'])
def resize_batch():
    """Resize multiple images and compress them into a ZIP."""
    filenames = request.form.get('filenames').split(',')
    output_files = []

    for filename in filenames:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        name, ext = os.path.splitext(filename)
        output_filename = f"{name}_rsz{ext}"
        format_conversion = request.form.get('format', None)
        if format_conversion:
            output_filename = f"{name}_rsz.{format_conversion.lower()}"
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)

        command = build_imagemagick_command(
            filepath=filepath,
            output_path=output_path,
            width=request.form.get('width', DEFAULTS["width"]),
            height=request.form.get('height', DEFAULTS["height"]),
            percentage=request.form.get('percentage', DEFAULTS["percentage"]),
            quality=request.form.get('quality', DEFAULTS["quality"]),
            keep_ratio='keep_ratio' in request.form
        )

        try:
            subprocess.run(command[1], check=True)
            output_files.append(output_path)
        except Exception as e:
            flash_error(f"Error processing {filename}: {e}")

    if len(output_files) > 1:
        zip_suffix = datetime.now().strftime("%y%m%d-%H%M")
        zip_filename = f"batch_output_{zip_suffix}.zip"
        zip_path = os.path.join(app.config['OUTPUT_FOLDER'], zip_filename)
        with ZipFile(zip_path, 'w') as zipf:
            for file in output_files:
                zipf.write(file, os.path.basename(file))
        return redirect(url_for('download_batch', filename=zip_filename))
    elif len(output_files) == 1:
        return redirect(url_for('download', filename=os.path.basename(output_files[0])))
    else:
        return flash_error("No images processed."), redirect(url_for('index'))

@app.route('/download_batch/<filename>')
def download_batch(filename):
    """Serve the ZIP file for download."""
    zip_path = os.path.join(app.config['OUTPUT_FOLDER'], filename)
    return send_file(zip_path, as_attachment=True)

@app.route('/download/<filename>')
def download(filename):
    """Serve a single file for download."""
    filepath = os.path.join(app.config['OUTPUT_FOLDER'], filename)
    with open(filepath, 'rb') as f:
        response = Response(f.read(), mimetype='application/octet-stream')
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)