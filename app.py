from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash
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
        print(f"Error retrieving dimensions for {filepath}: {e}")
        return None


@app.route('/')
def index():
    """Homepage with upload options."""
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file uploads."""
    if 'file' not in request.files:
        flash('No file selected.')
        return redirect(url_for('index'))

    files = request.files.getlist('file')  # Multiple files support
    if not files or files[0].filename == '':
        flash('No file selected.')
        return redirect(url_for('index'))

    uploaded_files = []
    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            uploaded_files.append(filename)
        else:
            flash(f"Unsupported file format for {file.filename}.")

    # Redirect logic
    if len(uploaded_files) == 1:
        return redirect(url_for('resize_options', filename=uploaded_files[0]))
    elif len(uploaded_files) > 1:
        return redirect(url_for('resize_batch_options', filenames=','.join(uploaded_files)))
    else:
        flash('No valid files uploaded.')
        return redirect(url_for('index'))


@app.route('/upload_url', methods=['POST'])
def upload_url():
    """Handle image upload from a URL."""
    url = request.form.get('url')
    if not url:
        flash("No URL provided.")
        return redirect(url_for('index'))

    try:
        # Fetch the image from the URL
        response = requests.get(url, stream=True)
        response.raise_for_status()  # Raise error for bad status codes

        # Extract the filename from the URL
        filename = url.split("/")[-1]
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(filename))

        # Write the content to a file
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        flash(f"Image downloaded successfully: {filename}")
        return redirect(url_for('resize_options', filename=filename))
    except requests.exceptions.RequestException as e:
        flash(f"Error downloading image: {e}")
        return redirect(url_for('index'))


@app.route('/resize_options/<filename>')
def resize_options(filename):
    """Resize options page for a single image."""
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    dimensions = get_image_dimensions(filepath)  # Get real dimensions
    if not dimensions:
        flash("Unable to get image dimensions.")
        return redirect(url_for('index'))

    formats = ['jpg', 'png', 'webp']  # Placeholder formats
    width, height = dimensions
    return render_template('resize.html', filename=filename, width=width, height=height, formats=formats)


@app.route('/resize/<filename>', methods=['POST'])
def resize_image(filename):
    """Handle resizing or format conversion for a single image."""
    quality = request.form.get('quality', '100')  # Default quality is 100
    format_conversion = request.form.get('format', None)
    keep_ratio = 'keep_ratio' in request.form  # Checkbox for aspect ratio
    width = request.form.get('width', '')
    height = request.form.get('height', '')
    percentage = request.form.get('percentage', '')

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    name, ext = os.path.splitext(filename)
    output_filename = f"{name}_rsz{ext}"  # Add the `_rsz` suffix before extension
    if format_conversion:
        output_filename = f"{name}_rsz.{format_conversion.lower()}"  # Apply format conversion
    output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)

    try:
        # Build the ImageMagick command
        command = ["/usr/local/bin/magick", filepath]

        if width.isdigit() and height.isdigit():
            if keep_ratio:
                resize_value = f"{width}x{height}"  # Keep aspect ratio
            else:
                resize_value = f"{width}x{height}!"  # Allow deformation
            command.extend(["-resize", resize_value])
        elif percentage.isdigit() and 0 < int(percentage) <= 100:
            resize_value = f"{percentage}%"
            command.extend(["-resize", resize_value])

        # Add quality if specified
        if quality.isdigit() and 1 <= int(quality) <= 100:
            command.extend(["-quality", quality])

        # Output path
        command.append(output_path)

        # Run the ImageMagick command
        subprocess.run(command, check=True)

        flash(f'Image processed successfully: {output_filename}')
        return redirect(url_for('download', filename=output_filename))
    except Exception as e:
        flash(f"Error processing image: {e}")
        return redirect(url_for('resize_options', filename=filename))


@app.route('/resize_batch_options/<filenames>')
def resize_batch_options(filenames):
    """Resize options page for batch processing."""
    files = filenames.split(',')
    formats = ['jpg', 'png', 'webp']  # Placeholder formats
    return render_template('resize_batch.html', files=files, formats=formats)


@app.route('/resize_batch', methods=['POST'])
def resize_batch():
    """Resize multiple images and compress them into a ZIP."""
    filenames = request.form.get('filenames').split(',')
    quality = request.form.get('quality', '100')
    format_conversion = request.form.get('format', None)
    keep_ratio = 'keep_ratio' in request.form
    width = request.form.get('width', '')
    height = request.form.get('height', '')
    percentage = request.form.get('percentage', '')

    output_files = []
    for filename in filenames:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        name, ext = os.path.splitext(filename)
        output_filename = f"{name}_rsz{ext}"
        if format_conversion:
            output_filename = f"{name}_rsz.{format_conversion.lower()}"
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)

        try:
            command = ["/usr/local/bin/magick", filepath]

            if width.isdigit() and height.isdigit():
                if keep_ratio:
                    resize_value = f"{width}x{height}"
                else:
                    resize_value = f"{width}x{height}!"
                command.extend(["-resize", resize_value])
            elif percentage.isdigit() and 0 < int(percentage) <= 100:
                resize_value = f"{percentage}%"
                command.extend(["-resize", resize_value])

            if quality.isdigit() and 1 <= int(quality) <= 100:
                command.extend(["-quality", quality])

            command.append(output_path)
            subprocess.run(command, check=True)
            output_files.append(output_path)
        except Exception as e:
            flash(f"Error processing {filename}: {e}")

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
        flash("No images processed.")
        return redirect(url_for('index'))


@app.route('/download_batch/<filename>')
def download_batch(filename):
    """Serve the ZIP file for download."""
    return send_from_directory(app.config['OUTPUT_FOLDER'], filename, as_attachment=True)


@app.route('/download/<filename>')
def download(filename):
    """Serve a single file for download."""
    return send_from_directory(app.config['OUTPUT_FOLDER'], filename, as_attachment=True)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)