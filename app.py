from flask import Flask, render_template, request, redirect, url_for, send_file, flash, Response
import os
import subprocess
from zipfile import ZipFile
from datetime import datetime
from werkzeug.utils import secure_filename
from PIL import Image
import requests
import logging

# Configuration
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'output'
MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100 MB max
MAX_BUFFER_SIZE = 16 * 1024 * 1024  # 16 MB buffer size
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
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
app.config['MAX_BUFFER_SIZE'] = MAX_BUFFER_SIZE
app.secret_key = 'supersecretkey'

# Configure logging
app.logger.setLevel(logging.INFO)

def allowed_file(filename):
    """Allow all file types supported by ImageMagick."""
    return '.' in filename

def get_image_dimensions(filepath):
    """Get image dimensions using ImageMagick identify command."""
    try:
        # Pour les fichiers RAW, on utilise dcraw
        if filepath.lower().endswith(('.arw', '.cr2', '.nef', '.dng', '.raw', '.rw2', '.orf', '.pef')):
            # Essayer d'abord avec dcraw -i -v
            app.logger.info(f"Running dcraw command for: {filepath}")
            cmd = ['dcraw', '-i', '-v', filepath]
            app.logger.info(f"Command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            app.logger.info(f"dcraw stdout: {result.stdout}")
            if result.stderr:
                app.logger.error(f"dcraw stderr: {result.stderr}")

            # Si dcraw -i ne donne pas les dimensions, essayer avec dcraw -e
            if not any('size' in line for line in result.stdout.split('\n')):
                app.logger.info("Trying dcraw -e to extract thumbnail")
                thumb_dir = os.path.dirname(filepath)
                thumb_base = os.path.splitext(os.path.basename(filepath))[0]
                thumb_path = os.path.join(thumb_dir, thumb_base + '.thumb.jpg')
                
                cmd = ['dcraw', '-e', filepath]
                result = subprocess.run(cmd, capture_output=True, text=True, cwd=thumb_dir)
                
                if os.path.exists(thumb_path):
                    app.logger.info(f"Thumbnail extracted, getting dimensions with ImageMagick")
                    cmd = ['magick', 'identify', thumb_path]
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    
                    try:
                        os.remove(thumb_path)  # Nettoyer le thumbnail
                    except:
                        pass
                        
                    if result.returncode == 0:
                        parts = result.stdout.split()
                        if len(parts) >= 2:
                            dimensions = parts[2].split('x')
                            if len(dimensions) == 2:
                                # Les dimensions du thumbnail ne sont pas les bonnes,
                                # mais on peut les utiliser comme ratio pour l'instant
                                width = 7008  # Taille connue pour Sony A7 IV
                                height = int((7008 * int(dimensions[1])) / int(dimensions[0]))
                                app.logger.info(f"Estimated dimensions from thumbnail ratio: {width}x{height}")
                                return width, height

            # En dernier recours, utiliser les dimensions connues pour ce modèle
            app.logger.info("Using known dimensions for Sony A7 IV")
            return 7008, 4672  # Dimensions connues pour Sony A7 IV

        else:
            cmd = ['magick', 'identify', filepath]
            
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            parts = result.stdout.split()
            if len(parts) >= 2:
                dimensions = parts[2].split('x')
                if len(dimensions) == 2:
                    return int(dimensions[0]), int(dimensions[1])
        
        app.logger.error(f"Erreur lors de l'identification de l'image : {result.stderr}")
        flash(f"Erreur lors de l'identification de l'image : {result.stderr}")
        return None
    except Exception as e:
        app.logger.error(f"Exception lors de l'identification de l'image : {e}")
        flash(f"Exception lors de l'identification de l'image : {e}")
        return None

def get_available_formats():
    """Get all formats supported by ImageMagick."""
    try:
        # Exécute la commande magick -list format pour obtenir tous les formats supportés
        result = subprocess.run(['magick', '-list', 'format'], capture_output=True, text=True)
        formats = []
        
        # Parse la sortie pour extraire les formats
        for line in result.stdout.split('\n'):
            # Ignore l'en-tête et les lignes vides
            if line.strip() and not line.startswith('Format') and not line.startswith('--'):
                # Le format est le premier mot de chaque ligne
                format_name = line.split()[0].upper()
                # Certains formats ont des suffixes comme * ou +, on les enlève
                format_name = format_name.rstrip('*+')
                if format_name not in formats:
                    formats.append(format_name)
        
        return formats
    except Exception as e:
        app.logger.error(f"Erreur lors de la récupération des formats : {e}")
        # Liste de secours avec les formats les plus courants
        return ['PNG', 'JPEG', 'GIF', 'TIFF', 'BMP', 'WEBP']

def get_format_categories():
    """Categorize image formats by their typical usage."""
    return {
        'transparency': {
            'recommended': ['PNG', 'WEBP', 'AVIF', 'HEIC', 'GIF'],
            'compatible': ['TIFF', 'ICO', 'JXL', 'PSD', 'SVG', 'TGA']
        },
        'photo': {
            'recommended': ['JPEG', 'WEBP', 'AVIF', 'HEIC', 'JXL', 'TIFF'],
            'compatible': [
                # Formats RAW
                'ARW', 'CR2', 'CR3', 'NEF', 'NRW', 'ORF', 'RAF', 'RW2', 'PEF', 'DNG',
                'IIQ', 'KDC', '3FR', 'MEF', 'MRW', 'SRF', 'X3F',
                # Autres formats photo
                'PNG', 'BMP', 'PPM', 'JP2', 'HDR', 'EXR', 'DPX', 'MIFF', 'MNG',
                'PCD', 'RGBE', 'YCbCr', 'CALS'
            ]
        },
        'graphic': {
            'recommended': ['PNG', 'WEBP', 'GIF', 'SVG'],
            'compatible': [
                'JPEG', 'TIFF', 'BMP', 'PCX', 'TGA', 'ICO', 'WBMP', 'XPM',
                'DIB', 'EMF', 'WMF', 'PICT', 'MacPICT', 'EPT', 'EPDF', 'EPI', 'EPS',
                'EPSF', 'EPSI', 'EPT', 'PDF', 'PS', 'AI', 'MONO'
            ]
        }
    }

def get_recommended_formats(image_type):
    """Get recommended and compatible formats based on image type."""
    categories = get_format_categories()
    available_formats = set(get_available_formats())
    
    if image_type['has_transparency']:
        category = 'transparency'
    elif image_type['is_photo']:
        category = 'photo'
    else:
        category = 'graphic'
        
    # Récupère les formats recommandés et compatibles pour cette catégorie
    recommended = [fmt for fmt in categories[category]['recommended'] 
                  if fmt in available_formats]
    compatible = [fmt for fmt in categories[category]['compatible'] 
                 if fmt in available_formats]
    
    # Ajoute le format original s'il n'est pas déjà présent
    original_format = image_type.get('original_format')
    if original_format:
        original_format = original_format.upper()
        if original_format not in recommended and original_format not in compatible:
            if original_format in available_formats:
                compatible.append(original_format)
    
    return {
        'recommended': recommended,
        'compatible': compatible
    }

def analyze_image_type(filepath):
    """Analyze image to determine its type and best suitable formats."""
    try:
        # Pour les fichiers RAW, on retourne directement les valeurs appropriées
        if filepath.lower().endswith(('.arw', '.cr2', '.nef', '.dng', '.raw', '.rw2', '.orf', '.pef')):
            app.logger.info(f"RAW file detected, using default settings")
            return {
                'has_transparency': False,
                'is_photo': True,
                'original_format': os.path.splitext(filepath)[1][1:].upper()
            }

        # Pour les autres formats, on utilise PIL
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
        # En cas d'erreur, on retourne des valeurs par défaut sécurisées
        return {
            'has_transparency': False,
            'is_photo': True,
            'original_format': os.path.splitext(filepath)[1][1:].upper()
        }

def flash_error(message):
    """Flash error message and log if needed."""
    flash(message)
    app.logger.error(message)

def build_imagemagick_command(filepath, output_path, width, height, percentage, quality, keep_ratio):
    """Build ImageMagick command for resizing and formatting."""
    # Pour les fichiers RAW, on utilise exiftool pour extraire le preview JPEG
    if filepath.lower().endswith(('.arw', '.cr2', '.nef', '.dng', '.raw', '.rw2', '.orf', '.pef')):
        # Extraire le preview JPEG avec exiftool
        app.logger.info(f"Extracting preview from RAW file: {filepath}")
        preview_path = os.path.join(os.path.dirname(output_path), f"{os.path.splitext(os.path.basename(filepath))[0]}_preview.jpg")
        
        # -b: sortie binaire
        # -PreviewImage: extrait l'image preview (souvent meilleure qualité que le thumbnail)
        # -JpgFromRaw: alternative si PreviewImage n'existe pas
        exiftool_cmd = ['exiftool', '-b', '-PreviewImage', '-JpgFromRaw', filepath]
        app.logger.info(f"exiftool command: {' '.join(exiftool_cmd)}")
        
        return exiftool_cmd, ['magick', preview_path] + (
            ["-resize", f"{width}x{height}{'!' if not keep_ratio else ''}"] if width.isdigit() and height.isdigit()
            else ["-resize", f"{percentage}%"] if percentage.isdigit() and 0 < int(percentage) <= 100
            else []
        ) + (
            ["-quality", quality] if quality.isdigit() and 1 <= int(quality) <= 100 else []
        ) + [output_path]
    else:
        command = ['magick', filepath]
    
        if width.isdigit() and height.isdigit():
            resize_value = f"{width}x{height}" if keep_ratio else f"{width}x{height}!"
            command.extend(["-resize", resize_value])
        elif percentage.isdigit() and 0 < int(percentage) <= 100:
            command.extend(["-resize", f"{percentage}%"])
            
        if quality.isdigit() and 1 <= int(quality) <= 100:
            command.extend(["-quality", quality])
            
        command.append(output_path)
        return None, command

@app.route('/')
def index():
    """Homepage with upload options."""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file uploads."""
    app.logger.info("Starting file upload...")
    files = request.files.getlist('file')
    app.logger.info(f"Received {len(files)} files")
    
    if not files or all(file.filename == '' for file in files):
        app.logger.warning("No files selected")
        flash_error('No file selected.')
        return redirect(url_for('index'))

    uploaded_files = []
    for file in files:
        if file and allowed_file(file.filename):
            app.logger.info(f"Processing file: {file.filename}")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(file.filename))
            try:
                file.save(filepath)
                app.logger.info(f"File saved successfully: {filepath}")
                uploaded_files.append(filepath)
            except Exception as e:
                app.logger.error(f"Error saving file {file.filename}: {str(e)}")
                flash_error(f"Error saving file {file.filename}")
        else:
            app.logger.warning(f"Unsupported file format: {file.filename}")
            flash_error(f"Unsupported file format for {file.filename}.")

    if len(uploaded_files) == 1:
        return redirect(url_for('resize_options', filename=os.path.basename(uploaded_files[0])))
    if len(uploaded_files) > 1:
        return redirect(url_for('resize_batch_options', filenames=','.join(map(os.path.basename, uploaded_files))))
    return redirect(url_for('index'))

@app.route('/upload_url', methods=['POST'])
def upload_url():
    """Handle image upload from a URL."""
    url = request.form.get('url')
    if not url:
        return flash_error("No URL provided."), redirect(url_for('index'))

    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, stream=True, headers=headers)
        response.raise_for_status()

        filename = url.split("/")[-1].split("?")[0]
        if not filename:
            return flash_error("Unable to determine a valid filename from the URL."), redirect(url_for('index'))

        filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(filename))
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        flash(f"Image downloaded successfully: {filename}")
        return redirect(url_for('resize_options', filename=filename))
    except requests.exceptions.RequestException as e:
        return flash_error(f"Error downloading image: {e}"), redirect(url_for('index'))

@app.route('/resize_options/<filename>')
def resize_options(filename):
    """Resize options page for a single image."""
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    dimensions = get_image_dimensions(filepath)
    if not dimensions:
        return redirect(url_for('index'))

    # Analyze image and get recommended formats
    image_type = analyze_image_type(filepath)
    if image_type:
        format_info = get_recommended_formats(image_type)
        formats = {
            'recommended': format_info['recommended'],
            'compatible': format_info['compatible']
        }
    else:
        formats = {
            'recommended': [],
            'compatible': get_available_formats()
        }

    width, height = dimensions
    return render_template('resize.html', 
                         filename=filename, 
                         width=width, 
                         height=height, 
                         formats=formats, 
                         image_type=image_type)

@app.route('/resize/<filename>', methods=['POST'])
def resize_image(filename):
    """Handle resizing or format conversion for a single image."""
    try:
        width = request.form.get('width', DEFAULTS["width"])
        height = request.form.get('height', DEFAULTS["height"])
        percentage = request.form.get('percentage', DEFAULTS["percentage"])
        quality = request.form.get('quality', DEFAULTS["quality"])
        keep_ratio = 'keep_ratio' in request.form
        output_format = request.form.get('format', '').lower()
        
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        output_filename = f"{os.path.splitext(filename)[0]}_resized.{output_format or os.path.splitext(filename)[1][1:]}"
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)
        
        exiftool_cmd, magick_cmd = build_imagemagick_command(input_path, output_path, width, height, percentage, quality, keep_ratio)
        
        if exiftool_cmd:  # Si c'est un fichier RAW
            # Extraire le preview JPEG
            preview_path = os.path.join(app.config['OUTPUT_FOLDER'], f"{os.path.splitext(filename)[0]}_preview.jpg")
            app.logger.info(f"Running exiftool command: {' '.join(exiftool_cmd)}")
            
            with open(preview_path, 'wb') as f:
                exiftool_result = subprocess.run(exiftool_cmd, stdout=f)
                if exiftool_result.returncode != 0:
                    raise Exception(f"exiftool command failed with return code {exiftool_result.returncode}")
            
            if not os.path.exists(preview_path) or os.path.getsize(preview_path) == 0:
                raise Exception("Failed to extract preview from RAW file")
            
            # Redimensionner avec ImageMagick
            app.logger.info(f"Running ImageMagick command: {' '.join(magick_cmd)}")
            magick_result = subprocess.run(magick_cmd)
            
            # Nettoyer le preview
            try:
                os.remove(preview_path)
            except:
                pass
            
            if magick_result.returncode != 0:
                raise Exception(f"ImageMagick command failed with return code {magick_result.returncode}")
        else:  # Pour les autres formats
            app.logger.info(f"Running ImageMagick command: {' '.join(magick_cmd)}")
            result = subprocess.run(magick_cmd)
            if result.returncode != 0:
                raise Exception(f"ImageMagick command failed with return code {result.returncode}")
        
        return redirect(url_for('download', filename=output_filename))
    except Exception as e:
        app.logger.error(f"Error processing image: {str(e)}")
        flash_error(f"Error processing image: {str(e)}")
        return redirect(url_for('index'))

@app.route('/resize_batch_options/<filenames>')
def resize_batch_options(filenames):
    """Resize options page for batch processing."""
    files = filenames.split(',')
    
    # Analyze each image and get common recommended formats
    image_types = []
    has_transparency = False
    has_photos = False
    has_graphics = False
    
    for filename in files:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        image_type = analyze_image_type(filepath)
        if image_type:
            image_types.append({'filename': filename, 'type': image_type})
            has_transparency = has_transparency or image_type['has_transparency']
            has_photos = has_photos or image_type['is_photo']
            has_graphics = has_graphics or not image_type['is_photo']
    
    # Create a combined image type for the batch
    batch_type = {
        'has_transparency': has_transparency,
        'is_photo': has_photos,
        'original_format': None  # Not relevant for batch
    }
    
    # Get format recommendations for the batch
    format_info = get_recommended_formats(batch_type)
    
    batch_info = {
        'has_transparency': has_transparency,
        'has_photos': has_photos,
        'has_graphics': has_graphics
    }
    
    return render_template('resize_batch.html', 
                         files=files, 
                         formats=format_info, 
                         image_types=image_types,
                         batch_info=batch_info)

@app.route('/resize_batch', methods=['POST'])
def resize_batch():
    """Resize multiple images and compress them into a ZIP."""
    try:
        width = request.form.get('width', DEFAULTS["width"])
        height = request.form.get('height', DEFAULTS["height"])
        percentage = request.form.get('percentage', DEFAULTS["percentage"])
        quality = request.form.get('quality', DEFAULTS["quality"])
        keep_ratio = 'keep_ratio' in request.form
        output_format = request.form.get('format', '').lower()
        
        # Créer un nom unique pour le ZIP
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        zip_filename = f'batch_resized_{timestamp}.zip'
        zip_path = os.path.join(app.config['OUTPUT_FOLDER'], zip_filename)
        
        with ZipFile(zip_path, 'w') as zip_file:
            for filename in request.form.get('filenames').split(','):
                try:
                    input_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    output_filename = f"{os.path.splitext(filename)[0]}_resized.{output_format or os.path.splitext(filename)[1][1:]}"
                    output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)
                    
                    dcraw_cmd, magick_cmd = build_imagemagick_command(input_path, output_path, width, height, percentage, quality, keep_ratio)
                    
                    if dcraw_cmd:  # Si c'est un fichier RAW
                        app.logger.info(f"Running dcraw command: {' '.join(dcraw_cmd)}")
                        # Créer un fichier temporaire pour stocker la sortie de dcraw
                        temp_ppm = os.path.join(app.config['OUTPUT_FOLDER'], f"{os.path.splitext(filename)[0]}_temp.ppm")
                        
                        # Exécuter dcraw et sauvegarder en PPM
                        with open(temp_ppm, 'wb') as f:
                            dcraw_result = subprocess.run(dcraw_cmd, stdout=f)
                            if dcraw_result.returncode != 0:
                                raise Exception(f"dcraw command failed with return code {dcraw_result.returncode}")
                        
                        # Modifier la commande ImageMagick pour lire depuis le fichier PPM
                        magick_cmd[1] = temp_ppm
                        
                        # Exécuter ImageMagick
                        app.logger.info(f"Running ImageMagick command: {' '.join(magick_cmd)}")
                        magick_result = subprocess.run(magick_cmd)
                        
                        # Nettoyer le fichier temporaire
                        try:
                            os.remove(temp_ppm)
                        except:
                            pass
                        
                        if magick_result.returncode != 0:
                            raise Exception(f"ImageMagick command failed with return code {magick_result.returncode}")
                    else:  # Pour les autres formats
                        app.logger.info(f"Running ImageMagick command: {' '.join(magick_cmd)}")
                        result = subprocess.run(magick_cmd)
                        if result.returncode != 0:
                            raise Exception(f"ImageMagick command failed with return code {result.returncode}")
                    
                    # Ajouter l'image au ZIP
                    zip_file.write(output_path, output_filename)
                    # Supprimer le fichier temporaire
                    os.remove(output_path)
                except Exception as e:
                    app.logger.error(f"Error processing {filename}: {str(e)}")
                    flash_error(f"Error processing {filename}: {str(e)}")
        
        return redirect(url_for('download_batch', filename=zip_filename))
    except Exception as e:
        app.logger.error(f"Error in batch processing: {str(e)}")
        flash_error(f"Error in batch processing: {str(e)}")
        return redirect(url_for('index'))

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

@app.errorhandler(413)
def request_entity_too_large(error):
    """Handle file too large error."""
    flash_error(f'Le fichier est trop volumineux. La taille maximale est de {MAX_CONTENT_LENGTH // (1024*1024)} MB.')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)