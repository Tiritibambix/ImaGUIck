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
app.secret_key = 'supersecretkey'
app.logger.setLevel(logging.INFO)

def allowed_file(filename):
    """Allow all image file types supported by ImageMagick, but block potentially dangerous extensions."""
    BLOCKED_EXTENSIONS = {'php', 'php3', 'php4', 'php5', 'phtml', 'exe', 'js', 'jsp', 'html', 'htm', 'sh', 'bash', 'py', 'pl'}
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    return ext and ext not in BLOCKED_EXTENSIONS

def secure_path(filepath):
    """Ensure the filepath is secure and within allowed directories."""
    try:
        abs_path = os.path.abspath(filepath)
        base_path = os.path.abspath(os.path.join(app.config['UPLOAD_FOLDER'], ''))
        output_path = os.path.abspath(os.path.join(app.config['OUTPUT_FOLDER'], ''))
        if not (abs_path.startswith(base_path) or abs_path.startswith(output_path)):
            return None
        return abs_path
    except Exception:
        return None

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
            result = subprocess.run(cmd, capture_output=True, text=True, shell=False)
            
            if result.returncode == 0 and result.stdout.strip():
                app.logger.info(f"Exiftool output received")
                dimensions = result.stdout.strip().split('\n')
                if len(dimensions) == 2:
                    try:
                        height = int(dimensions[0])
                        width = int(dimensions[1])
                        app.logger.info(f"Successfully parsed dimensions: {width}x{height}")
                        return width, height
                    except ValueError:
                        app.logger.warning("Could not parse dimensions from exiftool output")
                        pass
            
            return 7008, 4672  # Dimensions connues pour Sony A7 IV
        else:
            app.logger.info(f"Getting dimensions for non-ARW file")
            cmd = ['magick', 'identify', secure_file_path]
            app.logger.info(f"Running ImageMagick command")
            result = subprocess.run(cmd, capture_output=True, text=True, shell=False)
            if result.returncode != 0:
                raise Exception(f"Error getting image dimensions: {result.stderr}")
            
            match = re.search(r'\s(\d+)x(\d+)\s', result.stdout)
            if match:
                width = int(match.group(1))
                height = int(match.group(2))
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
    
    # PNG est toujours recommandé car c'est un excellent format sans perte
    recommended.add('PNG')
    
    if image_type.get('has_transparency'):
        recommended.update(['WEBP', 'AVIF'])
    
    if image_type.get('is_photo'):
        recommended.update(['JPEG', 'WEBP', 'AVIF', 'HEIC', 'DNG'])
    else:
        # Pour les graphiques, logos, etc.
        recommended.update(['WEBP', 'SVG'])
    
    # Cas spéciaux basés sur le format original
    if original_format:
        original_format = original_format.upper()
        if original_format in ['ARW', 'CR2', 'CR3', 'NEF', 'RAF', 'RW2', 'DNG']:
            # Format RAW - on ajoute les formats de haute qualité
            recommended.update(['TIFF', 'DNG'])
        elif original_format in ['GIF', 'WEBP', 'MNG', 'APNG']:
            # Format d'animation
            recommended.update(['GIF', 'WEBP', 'APNG'])
        elif original_format in ['ICO', 'CUR', 'ICON']:
            # Format d'icône
            recommended.add('ICO')
        elif original_format in ['SVG', 'EPS', 'AI', 'PDF']:
            # Format vectoriel
            recommended.update(['SVG', 'PDF', 'EPS'])
        elif original_format in ['PSD', 'XCF', 'PSB']:
            # Format d'édition
            recommended.update(['PSD', 'TIFF'])
        elif original_format in ['TIFF']:
            # Formats de haute qualité
            recommended.add('TIFF')
    
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
    app.logger.error(message)
    flash(message)
    return render_template('result.html', 
                         success=False, 
                         title='Error',
                         return_url=request.referrer)

def build_imagemagick_command(filepath, output_path, width, height, percentage, quality, keep_ratio,
                         auto_level=False, auto_gamma=False, use_1080p=False, use_sharpen=False, sharpen_level='standard'):
    """Build ImageMagick command for resizing and formatting."""
    if not secure_path(filepath) or not secure_path(output_path):
        return None

    command = ['magick', filepath]

    # Apply auto corrections in optimal order
    if auto_gamma:
        command.append('-auto-gamma')
    if auto_level:
        command.append('-auto-level')

    # Apply sharpening with specific parameters based on level
    if use_sharpen:
        sharpen_params = {
            'low': '1x0.4+0.02+0.0',
            'standard': '1x0.5+0.02+0.0',
            'high': '1x0.6+0.02+0.0',
            'heavy': '1x0.6+0.02+0.5'
        }
        sharpen_value = sharpen_params.get(sharpen_level, '1x0.5+0.02+0.0')
        app.logger.info(f"Applying sharpening with level {sharpen_level}: -unsharp {sharpen_value}")
        command.extend(['-unsharp', sharpen_value])

    # Handle 1080p resizing
    if use_1080p:
        # Force keep_ratio to True for 1080p
        command.extend(['-resize', '1080x1080>'])
    else:
        # Original resizing logic
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

    # Set quality
    if quality and quality != "100":
        try:
            quality_value = int(quality)
            if 1 <= quality_value <= 100:
                command.extend(['-quality', str(quality_value)])
        except ValueError:
            return None

    command.append(output_path)
    return command

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
    if request.method == 'POST':
        url = request.form.get('url', '').strip()
        if not url:
            flash('No URL provided')
            return redirect(url_for('index'))

        try:
            # Validate URL
            if not url.startswith(('http://', 'https://')):
                flash('Invalid URL scheme. Only HTTP and HTTPS are allowed.')
                return redirect(url_for('index'))

            # Set timeout and size limits
            response = requests.get(url, stream=True, timeout=10, verify=True)
            content_type = response.headers.get('content-type', '')
            
            if not content_type.startswith('image/'):
                flash('URL does not point to a valid image')
                return redirect(url_for('index'))

            # Limit file size to 50MB
            content_length = response.headers.get('content-length', 0)
            if content_length and int(content_length) > 50 * 1024 * 1024:
                flash('Image file too large (max 50MB)')
                return redirect(url_for('index'))

            # Create a secure filename
            filename = secure_filename(os.path.basename(url.split('?')[0]))
            if not filename:
                filename = 'downloaded_image.jpg'
            
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            return redirect(url_for('resize_options', filename=filename))

        except requests.exceptions.RequestException as e:
            flash(f'Error downloading image: {str(e)}')
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
        auto_level = request.form.get('auto_level') == 'on'
        auto_gamma = request.form.get('auto_gamma') == 'on'
        use_sharpen = request.form.get('use_sharpen') == 'on'
        sharpen_level = request.form.get('sharpen_level', 'standard')
        
        app.logger.info(f"Processing resize request for {filename}")
        app.logger.info(f"Sharpening: enabled={use_sharpen}, level={sharpen_level}")
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
            return render_template('result.html', 
                                success=False, 
                                title='Error',
                                return_url=url_for('resize_options', filename=filename))

        # Créer un nom de fichier pour la sortie
        base_name = os.path.splitext(filename)[0]
        if output_format:
            output_filename = f"{base_name}_resized.{output_format.lower()}"
        else:
            output_filename = f"{base_name}_resized{os.path.splitext(filename)[1]}"
            
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)
        app.logger.info(f"Output path: {output_path}")
        
        # Préparer la commande
        command = build_imagemagick_command(
            filepath=filepath,
            output_path=output_path,
            width=width,
            height=height,
            percentage=request.form.get('percentage', DEFAULTS["percentage"]),
            quality=request.form.get('quality', DEFAULTS["quality"]),
            keep_ratio=keep_ratio,
            auto_level=auto_level,
            auto_gamma=auto_gamma,
            use_1080p=request.form.get('use_1080p') == 'on',
            use_sharpen=request.form.get('use_sharpen') == 'on',
            sharpen_level=request.form.get('sharpen_level', 'standard')
        )
        
        if not command:
            flash('Error preparing resize command')
            return render_template('result.html', 
                                success=False, 
                                title='Error',
                                return_url=url_for('resize_options', filename=filename))
            
        # Exécuter la commande
        try:
            app.logger.info(f"Executing command: {' '.join(command)}")
            subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            error_message = f"Error during image processing: {e.stderr}"
            app.logger.error(error_message)
            flash(error_message)
            return render_template('result.html', 
                                success=False, 
                                title='Error',
                                return_url=url_for('resize_options', filename=filename))
                
        flash('Image processed successfully!')
        return render_template('result.html',
                            success=True,
                            title='Success',
                            filename=output_filename,
                            batch=False)

    except Exception as e:
        app.logger.error(f"Error during resize: {str(e)}")
        flash(f'Error during resize: {str(e)}')
        return render_template('result.html',
                            success=False,
                            title='Error',
                            return_url=url_for('resize_options', filename=filename))

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

    # Collecter les informations détaillées pour chaque image
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
            # Mettre à jour les informations du batch
            if image_type.get('has_transparency'):
                batch_info['has_transparency'] = True
            if image_type.get('is_photo'):
                batch_info['has_photos'] = True
            if not image_type.get('is_photo'):
                batch_info['has_graphics'] = True
            
            # Ajouter les informations détaillées de l'image
            image_types.append({
                'filename': filename,
                'type': image_type
            })

    # Récupérer les formats disponibles basés sur le premier fichier
    formats = get_available_formats(first_file_path)

    return render_template('resize_batch.html',
                         files=filenames,
                         formats=formats,
                         batch_info=batch_info,
                         image_types=image_types,
                         defaults=DEFAULTS)

@app.route('/resize_batch', methods=['POST'])
def resize_batch():
    """Resize multiple images and compress them into a ZIP."""
    if 'filenames' not in request.form:
        flash('No files selected')
        return render_template('result.html',
                            success=False,
                            title='Error',
                            return_url=url_for('index'))

    filenames = request.form['filenames'].split(',')
    if not filenames:
        flash('No files selected')
        return render_template('result.html',
                            success=False,
                            title='Error',
                            return_url=url_for('index'))

    # Créer un dossier temporaire pour les fichiers traités
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    batch_folder = os.path.join(app.config['OUTPUT_FOLDER'], f'batch_{timestamp}')
    os.makedirs(batch_folder, exist_ok=True)

    width = request.form.get('width', DEFAULTS["width"])
    height = request.form.get('height', DEFAULTS["height"])
    keep_ratio = 'keep_ratio' in request.form
    output_format = request.form.get('format', '').upper()
    auto_level = request.form.get('auto_level') == 'on'
    auto_gamma = request.form.get('auto_gamma') == 'on'

    output_files = []
    processed = False
    errors = []

    for filename in filenames:
        try:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if not os.path.isfile(filepath):
                errors.append(f'File not found: {filename}')
                continue

            output_filename = f'resized_{filename}'
            if output_format:
                output_filename = f'{os.path.splitext(output_filename)[0]}.{output_format.lower()}'
            output_path = os.path.join(batch_folder, output_filename)

            # Construire et exécuter la commande de redimensionnement
            command = build_imagemagick_command(
                filepath=filepath,
                output_path=output_path,
                width=width,
                height=height,
                percentage=request.form.get('percentage', DEFAULTS["percentage"]),
                quality=request.form.get('quality', DEFAULTS["quality"]),
                keep_ratio=keep_ratio,
                auto_level=auto_level,
                auto_gamma=auto_gamma,
                use_1080p=request.form.get('use_1080p') == 'on',
                use_sharpen=request.form.get('use_sharpen') == 'on',
                sharpen_level=request.form.get('sharpen_level', 'standard')
            )

            if not command:
                app.logger.error(f"Error preparing resize command for {filename}")
                continue

            # Exécuter la commande
            try:
                app.logger.info(f"Executing command: {' '.join(command)}")
                subprocess.run(command, check=True, capture_output=True, text=True)
                output_files.append(output_path)
                processed = True
            except subprocess.CalledProcessError as e:
                error_message = f"Error processing {filename}: {e.stderr}"
                app.logger.error(error_message)
                flash(error_message)
                continue

        except Exception as e:
            error_msg = f"Error processing {filename}: {str(e)}"
            app.logger.error(error_msg)
            errors.append(error_msg)

    if not processed:
        app.logger.error("No images processed.")
        flash('No images were processed successfully')
        if errors:
            for error in errors:
                flash(error)
        return render_template('result.html',
                            success=False,
                            title='Batch Processing Failed',
                            return_url=request.referrer)

    # Créer le fichier ZIP
    zip_filename = f'batch_resized_{timestamp}.zip'
    zip_path = os.path.join(app.config['OUTPUT_FOLDER'], zip_filename)
    
    try:
        with ZipFile(zip_path, 'w') as zipf:
            for file in output_files:
                zipf.write(file, os.path.basename(file))
        
        if errors:
            flash('Some files were processed with errors:')
            for error in errors:
                flash(error)
        else:
            flash('All files processed successfully!')
            
        return render_template('result.html',
                            success=True,
                            title='Batch Processing Complete',
                            filename=zip_filename,
                            batch=True)

    except Exception as e:
        app.logger.error(f"Error creating ZIP file: {str(e)}")
        flash('Error creating ZIP file')
        return render_template('result.html',
                            success=False,
                            title='Error',
                            return_url=request.referrer)

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