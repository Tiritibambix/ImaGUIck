from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash
import os
import subprocess
import requests
from werkzeug.utils import secure_filename

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

# Page d'accueil
@app.route('/')
def index():
    return render_template('index.html')

# Téléchargement d'une image depuis l'ordinateur
@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'GET':
        return redirect(url_for('index'))

    if 'file' not in request.files:
        flash('Aucun fichier sélectionné.')
        return redirect(url_for('index'))

    file = request.files['file']
    if file.filename == '':
        flash('Aucun fichier sélectionné.')
        return redirect(url_for('index'))

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        flash(f'Fichier {filename} uploadé avec succès.')
        return redirect(url_for('resize_options', filename=filename))
    else:
        extensions = ', '.join(ALLOWED_EXTENSIONS)
        flash(f"Format de fichier non supporté. Formats acceptés : {extensions}")
        return redirect(url_for('index'))

# Téléchargement d'une image via URL
@app.route('/upload_url', methods=['POST'])
def upload_url():
    url = request.form['url']
    if not url:
        flash('Veuillez entrer une URL valide.')
        return redirect(url_for('index'))
    try:
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            filename = secure_filename(os.path.basename(url.split("?")[0]))
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            with open(filepath, "wb") as f:
                f.write(response.content)
            flash(f'Image téléchargée depuis l’URL : {filename}')
            return redirect(url_for('resize_options', filename=filename))
        else:
            flash('Erreur lors du téléchargement de l’image.')
            return redirect(url_for('index'))
    except Exception as e:
        flash(f'Échec du téléchargement : {str(e)}')
        return redirect(url_for('index'))

# Page pour choisir les options de redimensionnement
@app.route('/resize_options/<filename>')
def resize_options(filename):
    return render_template('resize.html', filename=filename)

# Redimensionner l'image
@app.route('/resize/<filename>', methods=['POST'])
def resize_image(filename):
    resize_mode = request.form.get('resize_mode', '')
    quality = request.form.get('quality', '100')  # Valeur par défaut : 100%
    format_conversion = request.form.get('format', None)
    keep_ratio = 'keep_ratio' in request.form  # Checkbox pour garder le ratio
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    output_filename = filename
    output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)

    if format_conversion:
        output_filename = f"{os.path.splitext(filename)[0]}.{format_conversion.lower()}"
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)

    try:
        # Déterminer les options de redimensionnement
        if resize_mode == 'pixels':
            width = request.form.get('width', '')
            height = request.form.get('height', '')
            if not width.isdigit() or not height.isdigit():
                flash('Dimensions invalides.')
                return redirect(url_for('resize_options', filename=filename))
            resize_value = f"{width}x{height}" if not keep_ratio else f"{width}x{height}!"
        elif resize_mode == 'percent':
            percentage = request.form.get('percentage', '')
            if not percentage.isdigit() or int(percentage) <= 0 or int(percentage) > 100:
                flash('Pourcentage invalide.')
                return redirect(url_for('resize_options', filename=filename))
            resize_value = f"{percentage}%"
        else:
            flash('Mode de redimensionnement invalide.')
            return redirect(url_for('resize_options', filename=filename))

        # Commande ImageMagick
        command = ["/usr/local/bin/magick", "convert", filepath]
        command.extend(["-resize", resize_value])
        if quality.isdigit() and 1 <= int(quality) <= 100:
            command.extend(["-quality", quality])
        command.extend(["-strip", output_path])  # Supprime les métadonnées inutiles
        subprocess.run(command, check=True)

        flash(f'L’image a été redimensionnée avec succès sous le nom {output_filename}.')
        return redirect(url_for('download', filename=output_filename))
    except subprocess.CalledProcessError as e:
        flash(f"Erreur lors du traitement de l'image : {e}")
        return redirect(url_for('resize_options', filename=filename))
    except Exception as e:
        flash(f"Une erreur est survenue : {e}")
        return redirect(url_for('resize_options', filename=filename))

# Télécharger l'image redimensionnée
@app.route('/download/<filename>')
def download(filename):
    return send_from_directory(app.config['OUTPUT_FOLDER'], filename, as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)