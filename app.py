from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash
import os
import subprocess
import requests
from werkzeug.utils import secure_filename
from zipfile import ZipFile
from PIL import Image

# Configuration
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'output'
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'tiff', 'pdf'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER
app.secret_key = 'supersecretkey'


def allowed_file(filename):
    """Check if the file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_image_dimensions(filepath):
    """Get image dimensions as (width, height)."""
    try:
        with Image.open(filepath) as img:
            return img.size
    except Exception:
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


@app.route('/resize_options/<filename>')
def resize_options(filename):
    """Resize options page for a single image."""
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    dimensions = get_image_dimensions(filepath)
    if not dimensions:
        flash("Unable to get image dimensions.")
        return redirect(url_for('index'))
    width, height = dimensions
    return render_template('resize.html', filename=filename, width=width, height=height)


@app.route('/resize_batch_options/<filenames>')
def resize_batch_options(filenames):
    """Resize options page for batch processing."""
    files = filenames.split(',')
    return render_template('resize_batch.html', files=files)


@app.route('/resize_batch', methods=['POST'])
def resize_batch():
    """Resize multiple images and compress them into a ZIP."""
    filenames = request.form.getlist('filenames')
    quality = request.form.get('quality', '100')
    format_conversion = request.form.get('format', None)
    keep_ratio = 'keep_ratio' in request.form
    width = request.form.get('width', '')
    height = request.form.get('height', '')
    percentage = request.form.get('percentage', '')

    output_files = []
    for filename in filenames:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        output_filename = filename
        if format_conversion:
            output_filename = f"{os.path.splitext(filename)[0]}.{format_conversion.lower()}"
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)

        try:
            resize_value = determine_resize_value(width, height, percentage, keep_ratio)
            command = ["/usr/local/bin/magick", "convert", filepath, "-resize", resize_value]
            if quality.isdigit() and 1 <= int(quality) <= 100:
                command.extend(["-quality", quality])
            command.extend(["-strip", output_path])
            subprocess.run(command, check=True)
            output_files.append(output_path)
        except Exception as e:
            flash(f"Error with {filename}: {e}")

    if len(output_files) > 1:
        zip_path = os.path.join(app.config['OUTPUT_FOLDER'], "batch_output.zip")
        with ZipFile(zip_path, 'w') as zipf:
            for file in output_files:
                zipf.write(file, os.path.basename(file))
        return redirect(url_for('download_batch', filename="batch_output.zip"))
    elif len(output_files) == 1:
        return redirect(url_for('download', filename=os.path.basename(output_files[0])))
    else:
        flash("No images processed.")
        return redirect(url_for('index'))


def determine_resize_value(width, height, percentage, keep_ratio):
    """Determine resize value for ImageMagick."""
    if width.isdigit() and height.isdigit():
        return f"{width}x{height}" if not keep_ratio else f"{width}x{height}!"
    elif percentage.isdigit() and 0 < int(percentage) <= 100:
        return f"{percentage}%"
    else:
        raise ValueError("Invalid resize parameters.")


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
