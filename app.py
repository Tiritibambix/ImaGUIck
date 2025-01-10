from flask import Flask, render_template, request, redirect, url_for, send_file, flash, Response
import os
import subprocess
from zipfile import ZipFile
from datetime import datetime
from werkzeug.utils import secure_filename
from PIL import Image
import requests

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

def allowed_file(filename):
    """Allow all file types supported by ImageMagick."""
    return '.' in filename

def get_image_dimensions(filepath):
    """Get image dimensions as (width, height)."""
    try:
        with Image.open(filepath) as img:
            return img.size  # Returns (width, height)
    except Exception as e:
        flash_error(f"Error retrieving dimensions for {filepath}: {e}")
        return None

def get_available_formats():
    """Get a list of supported formats from ImageMagick."""
    try:
        result = subprocess.run(["/usr/local/bin/magick", "convert", "-list", "format"],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                text=True,
                                check=True)
        formats = []
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) > 1 and parts[1] in {"r", "rw", "rw+", "w"}:
                format_name = parts[0].lower().rstrip('*')
                formats.append(format_name)
        return formats
    except Exception as e:
        flash_error(f"Error fetching formats: {e}")
        return ["jpg", "png", "webp"]

def flash_error(message):
    """Flash error message and log if needed."""
    flash(message)
    print(message)

def build_imagemagick_command(filepath, output_path, width, height, percentage, quality, keep_ratio):
    """Build ImageMagick command for resizing and formatting."""
    command = ["/usr/local/bin/magick", filepath]
    if width.isdigit() and height.isdigit():
        resize_value = f"{width}x{height}" if keep_ratio else f"{width}x{height}!"
        command.extend(["-resize", resize_value])
    elif percentage.isdigit() and 0 < int(percentage) <= 100:
        command.extend(["-resize", f"{percentage}%"])
    if quality.isdigit() and 1 <= int(quality) <= 100:
        command.extend(["-quality", quality])
    command.append(output_path)
    return command

def analyze_image_type(filepath):
    """Analyze image to determine its type and best suitable formats."""
    try:
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
                'original_mode': img.mode
            }
    except Exception as e:
        flash_error(f"Error analyzing image: {e}")
        return None

def get_recommended_formats(image_type):
    """Get recommended and compatible formats based on image type."""
    recommended = []
    compatible = []
    
    # Formats RAW connus
    raw_formats = [
        'ARW',    # Sony
        'CR2',    # Canon
        'CR3',    # Canon nouvelle génération
        'NEF',    # Nikon
        'NRW',    # Nikon
        'ORF',    # Olympus
        'RAF',    # Fujifilm
        'RW2',    # Panasonic
        'PEF',    # Pentax
        'DNG',    # Format RAW universel
        'IIQ',    # Phase One
        'KDC',    # Kodak
        '3FR',    # Hasselblad
        'MEF',    # Mamiya
        'MRW',    # Minolta
        'SRF',    # Sony
        'X3F'     # Sigma
    ]
    
    if image_type['has_transparency']:
        # Formats avec excellent support de la transparence
        recommended.extend(['PNG', 'WebP', 'AVIF', 'HEIC'])  # Meilleurs formats modernes
        compatible.extend([
            'GIF',      # Transparence basique
            'TIFF',     # Bon support mais fichiers plus lourds
            'ICO',      # Pour les icônes
            'JXL',      # JPEG XL - nouveau format prometteur
            'PSD',      # Format Photoshop
            'SVG',      # Pour les graphiques vectoriels
        ])
        
    elif image_type['is_photo']:
        # Formats optimisés pour les photos
        recommended.extend([
            'JPEG',     # Standard pour les photos
            'WebP',     # Excellent compromis moderne
            'AVIF',     # Très bonne compression
            'HEIC',     # Format Apple haute efficacité
            'JXL'       # JPEG XL - excellent pour les photos
        ])
        compatible.extend([
            'PNG',      # Sans perte mais plus lourd
            'TIFF',     # Format professionnel
            'BMP',      # Format simple
            'PPM',      # Format pour photos
            'JP2',      # JPEG 2000
            'HDR',      # Pour les images HDR
            'EXR',      # Format HDR professionnel
            'DPX',      # Format cinéma numérique
        ] + raw_formats)  # Ajout des formats RAW pour les photos
        
    else:  # Graphics, illustrations, etc.
        # Formats optimisés pour les graphiques
        recommended.extend([
            'PNG',      # Parfait pour les graphiques nets
            'WebP',     # Bon compromis moderne
            'GIF',      # Idéal pour les animations simples
            'SVG'       # Pour les graphiques vectoriels
        ])
        compatible.extend([
            'JPEG',     # OK mais peut créer des artefacts
            'TIFF',     # Format professionnel
            'BMP',      # Format simple
            'PCX',      # Format historique
            'TGA',      # Format pour graphiques
            'ICO',      # Pour les icônes
            'WBMP',     # Pour les appareils limités
            'XPM',      # Pour les icônes X11
        ])
    
    # Ajouter le format original s'il n'est pas déjà présent
    original_format = image_type.get('original_format')
    if original_format:
        original_format = original_format.upper()
        # Si c'est un format RAW, on l'ajoute aux formats compatibles pour les photos
        if original_format in raw_formats and image_type['is_photo']:
            if original_format not in compatible:
                compatible.append(original_format)
        elif original_format not in recommended and original_format not in compatible:
            compatible.append(original_format)
    
    # Filtrer les formats en fonction de ce qui est réellement disponible
    available_formats = set(get_available_formats())
    recommended = [fmt for fmt in recommended if fmt in available_formats]
    compatible = [fmt for fmt in compatible if fmt in available_formats]
    
    return {
        'recommended': recommended,
        'compatible': compatible
    }

@app.route('/')
def index():
    """Homepage with upload options."""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file uploads."""
    files = request.files.getlist('file')
    if not files or all(file.filename == '' for file in files):
        return flash_error('No file selected.'), redirect(url_for('index'))

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
        subprocess.run(command, check=True)
        flash(f'Image processed successfully: {output_filename}')
        return redirect(url_for('download', filename=output_filename))
    except Exception as e:
        return flash_error(f"Error processing image: {e}"), redirect(url_for('resize_options', filename=filename))

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
            subprocess.run(command, check=True)
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