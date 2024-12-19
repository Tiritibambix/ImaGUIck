from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash
import os
import subprocess
from zipfile import ZipFile
from datetime import datetime

# Configuration
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'output'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER
app.secret_key = 'supersecretkey'


@app.route('/')
def index():
    """Homepage with upload options."""
    return render_template('index.html')


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


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)