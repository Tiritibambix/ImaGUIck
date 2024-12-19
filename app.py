from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash
import os
import subprocess
import requests
from werkzeug.utils import secure_filename
from PIL import Image
from zipfile import ZipFile

# Configuration
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'output'
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'tiff', 'pdf'}

# Création des répertoires nécessaires
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER
app.secret_key = 'supersecretkey'

# Vérifie si l'extension est autorisée
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Obtenir les dimensions d'une image
def get_image_dimensions(filepath):
    """Retourne les dimensions d'une image sous forme de tuple (width, height)."""
    try:
        with Image.open(filepath) as img:
            return img.size  # Retourne (width, height)
    except Exception as e:
        return None

# Détermine la valeur de redimensionnement
def determine_resize_value(width, height, percentage, keep_ratio):
    if width.isdigit() and height.isdigit():
        return f"{width}x{height}" if not keep_ratio else f"{width}x{height}!"
    elif percentage.isdigit() and 0 < int(percentage) <= 100:
        return f"{percentage}%"
    else:
        raise ValueError("Invalid resize parameters")

# Page d'accueil
@app.route('/')
def index():
    return render_template('index.html')

# Téléchargement d'une ou plusieurs images
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash('Aucun fichier sélectionné.')
        return redirect(url_for('index'))

    files = request.files.getlist('file')  # Récupérer tous les fichiers
    if not files or files[0].filename == '':
        flash('Aucun fichier sélectionné.')
        return redirect(url_for('index'))

    uploaded_files = []
    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            uploaded_files.append(filename)
        else:
            extensions = ', '.join(ALLOWED_EXTENSIONS)
            flash(f"Format non supporté pour {file.filename}. Formats acceptés : {extensions}")

    if len(uploaded_files) == 1:
        # Redirection pour un fichier unique
        return redirect(url_for('resize_options', filename=uploaded_files[0]))
    else:
        # Redirection pour un batch
        return redirect(url_for('resize_batch_options', filenames=','.join(uploaded_files)))

# Page pour choisir les options d'un batch
@app.route('/resize_batch_options/<filenames>')
def resize_batch_options(filenames):
    files = filenames.split(',')
    return render_template('resize_batch.html', files=files)

# Redimensionner un batch d'images
@app.route('/resize_batch', methods=['POST'])
def resize_batch():
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

        # Commande ImageMagick
        try:
            resize_value = determine_resize_value(width, height, percentage, keep_ratio)
            command = ["/usr/local/bin/magick", "convert", filepath, "-resize", resize_value]
            if quality.isdigit() and 1 <= int(quality) <= 100:
                command.extend(["-quality", quality])
            command.extend(["-strip", output_path])
            subprocess.run(command, check=True)
            output_files.append(output_path)
        except Exception as e:
            flash(f"Erreur avec {filename} : {str(e)}")

    if len(output_files) > 1:
        zip_path = os.path.join(app.config['OUTPUT_FOLDER'], "batch_output.zip")
        with ZipFile(zip_path, 'w') as zipf:
            for file in output_files:
                zipf.write(file, os.path.basename(file))
        return redirect(url_for('download_batch', filename="batch_output.zip"))
    elif len(output_files) == 1:
        return redirect(url_for('download', filename=os.path.basename(output_files[0])))
    else:
        flash("Aucune image traitée.")
        return redirect(url_for('index'))

# Télécharger un fichier ZIP
@app.route('/download_batch/<filename>')
def download_batch(filename):
    return send_from_directory(app.config['OUTPUT_FOLDER'], filename, as_attachment=True)

# Télécharger une image redimensionnée
@app.route('/download/<filename>')
def download(filename):
    return send_from_directory(app.config['OUTPUT_FOLDER'], filename, as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)