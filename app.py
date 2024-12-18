import os
import subprocess
import requests
from tkinter import Tk, Label, Entry, Button, filedialog, messagebox, Radiobutton, StringVar, Listbox, Scrollbar, END
from tkinter.ttk import Progressbar

# Liste des fichiers sélectionnés
file_list = []

def select_files():
    global file_list
    files = filedialog.askopenfilenames(filetypes=[("Image Files", "*.jpg;*.png")])
    if files:
        file_list.extend(files)
        update_file_list()

def add_url_image():
    url = url_entry.get()
    if not url:
        messagebox.showerror("Erreur", "Veuillez entrer une URL valide.")
        return
    try:
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            filename = os.path.basename(url.split("?")[0])
            save_path = os.path.join(os.getcwd(), filename)
            with open(save_path, "wb") as f:
                f.write(response.content)
            file_list.append(save_path)
            update_file_list()
        else:
            messagebox.showerror("Erreur", "Impossible de télécharger l'image.")
    except Exception as e:
        messagebox.showerror("Erreur", f"Échec du téléchargement : {str(e)}")

def update_file_list():
    file_listbox.delete(0, END)
    for file in file_list:
        file_listbox.insert(END, os.path.basename(file))

def clear_file_list():
    global file_list
    file_list = []
    file_listbox.delete(0, END)

def resize_images():
    if not file_list:
        messagebox.showerror("Erreur", "Aucune image sélectionnée.")
        return

    if resize_mode.get() == "pixels":
        width = width_entry.get()
        height = height_entry.get()
        if not width.isdigit() or not height.isdigit():
            messagebox.showerror("Erreur", "Veuillez entrer des dimensions valides.")
            return
        resize_value = f"{width}x{height}"  # Dimensions en pixels
    elif resize_mode.get() == "percent":
        percentage = percentage_entry.get()
        if not percentage.isdigit() or int(percentage) <= 0 or int(percentage) > 100:
            messagebox.showerror("Erreur", "Veuillez entrer un pourcentage valide (1-100).")
            return
        resize_value = f"{percentage}%"  # Pourcentage

    output_dir = filedialog.askdirectory()
    if not output_dir:
        return

    progress_bar["maximum"] = len(file_list)
    progress_bar["value"] = 0

    for i, file in enumerate(file_list):
        output_path = os.path.join(output_dir, os.path.basename(file))
        command = ["magick", "convert", file, "-resize", resize_value, output_path]
        subprocess.run(command)
        progress_bar["value"] += 1
        progress_bar_label.config(text=f"Traitement : {i + 1}/{len(file_list)}")
        root.update_idletasks()  # Mise à jour de la barre de progression

    messagebox.showinfo("Succès", f"Redimensionnement terminé. Images enregistrées dans : {output_dir}")
    progress_bar_label.config(text="")
    progress_bar["value"] = 0

# Interface graphique
root = Tk()
root.title("Image Resizer - GUI pour ImageMagick")

Label(root, text="Ajout d'images").pack()

# Ajout depuis le système de fichiers
Button(root, text="Ajouter des fichiers", command=select_files).pack(pady=5)

# Ajout depuis une URL
url_entry = Entry(root, width=50)
url_entry.pack(pady=5)
url_entry.insert(0, "Entrez l'URL de l'image ici")
Button(root, text="Ajouter depuis URL", command=add_url_image).pack(pady=5)

# Liste des fichiers
scrollbar = Scrollbar(root)
scrollbar.pack(side="right", fill="y")

file_listbox = Listbox(root, selectmode="multiple", width=50, height=10, yscrollcommand=scrollbar.set)
file_listbox.pack(pady=5)
scrollbar.config(command=file_listbox.yview)

Button(root, text="Vider la liste", command=clear_file_list).pack(pady=5)

# Mode de redimensionnement
resize_mode = StringVar(value="pixels")

Radiobutton(root, text="Dimensions (pixels)", variable=resize_mode, value="pixels").pack()
Label(root, text="Largeur :").pack()
width_entry = Entry(root)
width_entry.pack()

Label(root, text="Hauteur :").pack()
height_entry = Entry(root)
height_entry.pack()

Radiobutton(root, text="Pourcentage (%)", variable=resize_mode, value="percent").pack()
Label(root, text="Pourcentage :").pack()
percentage_entry = Entry(root)
percentage_entry.pack()

# Barre de progression
progress_bar_label = Label(root, text="")
progress_bar_label.pack(pady=5)

progress_bar = Progressbar(root, orient="horizontal", length=300, mode="determinate")
progress_bar.pack(pady=5)

# Bouton pour redimensionner
resize_button = Button(root, text="Redimensionner", command=resize_images)
resize_button.pack(pady=20)

root.mainloop()
