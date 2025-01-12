from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
import os
import subprocess
from zipfile import ZipFile
from datetime import datetime
from werkzeug.utils import secure_filename
from PIL import Image
import requests
import logging
import re
from urllib.parse import urlparse, urlencode, parse_qs

# Configuration
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'output'
DEFAULTS = {
    "quality": "100",
    "width": "",
    "height": "",
    "percentage": "",
}
LANGUAGES = ['en']

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER
app.secret_key = 'supersecretkey'
app.logger.setLevel(logging.INFO)

def url_for_with_lang(*args, **kwargs):
    return url_for(*args, **kwargs)

app.jinja_env.globals.update(url_for_with_lang=url_for_with_lang)

def allowed_file(filename):
    return '.' in filename

def get_image_dimensions(filepath):
    try:
        app.logger.info(f"Getting dimensions for non-ARW file: {filepath}")
        command = ['magick', 'identify', filepath]
        app.logger.info(f"Running ImageMagick command: {' '.join(command)}")
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        
        output = result.stdout.strip()
        match = re.search(r'\s(\d+)x(\d+)\s', output)
        if match:
            width, height = map(int, match.groups())
            return width, height
        else:
            raise ValueError(f"Could not parse dimensions from output: {output}")
            
    except subprocess.CalledProcessError as e:
        error_msg = f"Error getting image dimensions: {e.stderr}"
        app.logger.error(error_msg)
        raise ValueError(error_msg)
    except Exception as e:
        error_msg = f"Error getting image dimensions: {str(e)}"
        app.logger.error(error_msg)
        raise ValueError(error_msg)

def get_available_formats():
    try:
        result = subprocess.run(['magick', '-list', 'format'], capture_output=True, text=True)
        formats = []
        
        for line in result.stdout.split('\n'):
            if line.strip() and not line.startswith('Format') and not line.startswith('--'):
                format_name = line.split()[0].upper()
                format_name = format_name.rstrip('*+')
                if format_name not in formats:
                    formats.append(format_name)
        
        return formats
    except Exception as e:
        app.logger.error(f"Erreur lors de la récupération des formats : {e}")
        return ['PNG', 'JPEG', 'GIF', 'TIFF', 'BMP', 'WEBP']

def get_format_categories():
    return {
        'transparency': {
            'recommended': ['PNG', 'WEBP', 'AVIF', 'HEIC', 'GIF'],
            'compatible': ['TIFF', 'ICO', 'JXL', 'PSD', 'SVG', 'TGA']
        },
        'photo': {
            'recommended': ['JPEG', 'WEBP', 'AVIF', 'HEIC', 'JXL', 'TIFF'],
            'compatible': [
                'ARW', 'CR2', 'CR3', 'NEF', 'NRW', 'ORF', 'RAF', 'RW2', 'PEF', 'DNG',
                'IIQ', 'KDC', '3FR', 'MEF', 'MRW', 'SRF', 'X3F',
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
    categories = get_format_categories()
    available_formats = set(get_available_formats())
    
    if image_type['has_transparency']:
        category = 'transparency'
    elif image_type['is_photo']:
        category = 'photo'
    else:
        category = 'graphic'
        
    recommended = [fmt for fmt in categories[category]['recommended'] 
                  if fmt in available_formats]
    compatible = [fmt for fmt in categories[category]['compatible'] 
                 if fmt in available_formats]
    
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
    try:
        if filepath.lower().endswith('.arw'):
            app.logger.info(f"Analyzing RAW file: {filepath}")
            return {
                'has_transparency': False,
                'is_photo': True,
                'original_format': 'ARW'
            }
            
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
    except Exception as e:
        app.logger.error(f"Error analyzing image: {e}")
        return {
            'has_transparency': False,
            'is_photo': True,
            'original_format': None
        }

def flash_error(message):
    flash(message)
    app.logger.error(message)

def build_imagemagick_command(filepath, output_path, width, height, percentage, quality, keep_ratio):
    if filepath.lower().endswith('.arw'):
        app.logger.info(f"Processing ARW file: {filepath}")
        temp_jpeg = os.path.join(os.path.dirname(output_path), f"{os.path.splitext(os.path.basename(filepath))[0]}_preview.jpg")
        app.logger.info(f"Temporary JPEG will be saved as: {temp_jpeg}")
        
        exif_cmd = ['exiftool', '-b', '-JpgFromRaw', filepath]
        app.logger.info(f"Running exiftool command: {' '.join(exif_cmd)}")
        result = subprocess.run(exif_cmd, capture_output=True)
        
        if result.returncode == 0 and result.stdout.strip():
            app.logger.info("Successfully extracted JpgFromRaw")
            with open(temp_jpeg, 'wb') as f:
                f.write(result.stdout)
            app.logger.info(f"Saved JpgFromRaw to: {temp_jpeg}")
        else:
            app.logger.info("No JpgFromRaw found, trying PreviewImage...")
            exif_cmd = ['exiftool', '-b', '-PreviewImage', filepath]
            app.logger.info(f"Running exiftool command: {' '.join(exif_cmd)}")
            result = subprocess.run(exif_cmd, capture_output=True)
            if result.returncode == 0 and result.stdout.strip():
                app.logger.info("Successfully extracted PreviewImage")
                with open(temp_jpeg, 'wb') as f:
                    f.write(result.stdout)
                app.logger.info(f"Saved PreviewImage to: {temp_jpeg}")
            else:
                app.logger.error(f"Exiftool error: {result.stderr.decode('utf-8', errors='ignore')}")
                raise Exception("No preview image found in RAW file")
        
        magick_cmd = ['magick', temp_jpeg]
        
        if width.isdigit() and height.isdigit():
            resize_value = f"{width}x{height}" if keep_ratio else f"{width}x{height}!"
            magick_cmd.extend(["-resize", resize_value])
            app.logger.info(f"Adding resize parameters: {resize_value}")
        elif percentage.isdigit() and 0 < int(percentage) <= 100:
            magick_cmd.extend(["-resize", f"{percentage}%"])
            app.logger.info(f"Adding percentage resize: {percentage}%")
            
        if quality.isdigit() and 1 <= int(quality) <= 100:
            magick_cmd.extend(["-quality", quality])
            app.logger.info(f"Setting quality to: {quality}")
            
        magick_cmd.append(output_path)
        app.logger.info(f"Final ImageMagick command: {' '.join(magick_cmd)}")
        return None, magick_cmd, temp_jpeg
    else:
        app.logger.info(f"Processing non-ARW file: {filepath}")
        command = ['magick', filepath]
        
        if width.isdigit() and height.isdigit():
            resize_value = f"{width}x{height}" if keep_ratio else f"{width}x{height}!"
            command.extend(["-resize", resize_value])
            app.logger.info(f"Adding resize parameters: {resize_value}")
        elif percentage.isdigit() and 0 < int(percentage) <= 100:
            command.extend(["-resize", f"{percentage}%"])
            app.logger.info(f"Adding percentage resize: {percentage}%")
            
        if quality.isdigit() and 1 <= int(quality) <= 100:
            command.extend(["-quality", quality])
            app.logger.info(f"Setting quality to: {quality}")
            
        command.append(output_path)
        app.logger.info(f"Final ImageMagick command: {' '.join(command)}")
        return None, command, None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash(_('No file selected'), 'error')
        return redirect(url_for('index'))
        
    files = request.files.getlist('file')
    if not files or all(file.filename == '' for file in files):
        flash(_('Please select at least one file'), 'error')
        return redirect(url_for('index'))
        
    uploaded_files = []
    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            uploaded_files.append(filename)
            
    if len(uploaded_files) == 1:
        return redirect(url_for('resize_options', filename=uploaded_files[0]))
    elif len(uploaded_files) > 1:
        return redirect(url_for('resize_batch_options', filenames=','.join(uploaded_files)))
    else:
        flash(_('No valid files were uploaded'), 'error')
        return redirect(url_for('index'))

@app.route('/upload_url', methods=['POST'])
def upload_url():
    url = request.form.get('url', '').strip()
    if not url:
        flash(_('No file selected'), 'error')
        return redirect(url_for('index'))

    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        content_type = response.headers.get('content-type', '').lower()
        if not any(mime in content_type for mime in ['image/', 'application/octet-stream']):
            raise ValueError('URL does not point to an image')
            
        filename = secure_filename(os.path.basename(url))
        if not filename:
            filename = 'image.jpg'
            
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        flash(_('Image downloaded successfully: %(filename)s', filename=filename))
        return redirect(url_for('resize_options', filename=filename))
    except requests.exceptions.RequestException as e:
        flash(_('Error downloading image: %(error)s', error=str(e)), 'error')
        return redirect(url_for('index'))

@app.route('/resize_options/<filename>')
def resize_options(filename):
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    dimensions = get_image_dimensions(filepath)
    if not dimensions:
        return redirect(url_for('index'))

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
        flash(_('Image processed successfully: %(filename)s', filename=output_filename))
        return redirect(url_for('download', filename=output_filename))
    except Exception as e:
        flash(_('Error processing image: %(error)s', error=str(e)), 'error')
        return redirect(url_for('resize_options', filename=filename))

@app.route('/resize_batch_options/<filenames>')
def resize_batch_options(filenames):
    files = filenames.split(',')
    
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
    
    batch_type = {
        'has_transparency': has_transparency,
        'is_photo': has_photos,
        'original_format': None  
    }
    
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
            flash(_('Error processing %(filename)s: %(error)s', filename=filename, error=str(e)), 'error')

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
        flash(_('No images processed.'), 'error')
        return redirect(url_for('index'))

@app.route('/download_batch/<filename>')
def download_batch(filename):
    zip_path = os.path.join(app.config['OUTPUT_FOLDER'], filename)
    return send_file(zip_path, as_attachment=True)

@app.route('/download/<filename>')
def download(filename):
    filepath = os.path.join(app.config['OUTPUT_FOLDER'], filename)
    with open(filepath, 'rb') as f:
        response = Response(f.read(), mimetype='application/octet-stream')
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)