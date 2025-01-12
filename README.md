<p align="center">
  <img src="https://i.postimg.cc/rFRD78SG/Ima-GUIck-logo-NOWM-50.png" width="400" />
</p>

ImaGUIck is a simple and intuitive web application for batch image processing, providing a user-friendly graphical interface to resize and convert your images.

## ✨ Features

- 🖼️ **Single or Batch Image Processing**
- 📏 **Flexible Resizing Options**:
  - By specific dimensions (width x height)
  - By percentage
  - With or without aspect ratio preservation
- 🔄 **Support for Multiple Image Formats**:
  - Common formats (JPG, PNG, GIF, etc.)
  - RAW formats (ARW, etc.)
- 🌐 **Image Import from URL**
- 📦 **Batch Export in ZIP Format**
- 🎨 **Image Quality Control**
- 🔍 **Automatic Image Type Analysis**
- 💾 **Intelligent Format Recommendations**

## 🚀 Installation

### Prerequisites

- Python 3.9+
- Docker (optional)
- [`ImageMagick 7.1.1-41`](https://github.com/ImageMagick/ImageMagick/releases/tag/7.1.1-41)
- ExifTool

### Local Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/ImaGUIck.git
   cd ImaGUIck
   ```

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the application:
   ```bash
   python app.py
   ```

### Installation with Docker (supports amd64 and arm64)

##### 1. **Clone the repository**

```bash
git clone https://github.com/tiritibambix/ImaGUIck.git
cd ImaGUIck
```

##### 2. **Build the Docker image**

```bash
docker build -t imaguick .
```

##### 3. **Run the application**

```bash
docker run -it --rm \
    -v $(pwd)/uploads:/app/uploads \
    -v $(pwd)/output:/app/output \
    -p 5000:5000 \
    imaguick
```
 
##### Alternatively, you can use docker-compose to run the application:

```yaml
services:
  imaguick:
    stdin_open: true
    tty: true
    volumes:
      - ./uploads:/app/uploads
      - ./output:/app/output
    ports:
      - 5000:5000
    image: tiritibambix/imaguick:latest
networks: {}
```

## 🖥️ Usage

1. Access the application via your browser: `http://localhost:5000`

2. Choose your import method:
   - Upload file(s) from your computer
   - Import from a URL

3. Configure your processing options:
   - Output dimensions
   - Image quality
   - Output format

4. Start processing and download your images.

## 🛠️ Technical Architecture

### Technologies Used

- **Backend**: Flask (Python)
- **Image Processing**: 
  - ImageMagick 7.1.1-41
  - ExifTool
  - Pillow
- **Frontend**: HTML/CSS/JavaScript
- **Containerization**: Docker

### Project Structure

```
imaguick/
├── .github
|     ├── workflows
|     |     ├── docker-build-test.yml
|     |     ├── docker-build.yml
├── .gitignore                        # Excluded files for version control
├── Dockerfile                        # Instructions to build the Docker image
├── LICENSE                           # License for ImaGUIck and ImageMagick
├── README.md                         # Documentation
├── TODO.md
├── app.py                            # The main Python application
├── requirements.txt                  # Python dependencies
├── templates                         # HTML templates for the web interface
|     ├── index.html                  # Homepage
|     ├── resize.html                 # Resize options for individual images
|     ├── resize_batch.html           # Batch processing options

```

## 🤝 Contribution

Contributions are welcome! To contribute:

1. Fork the project
2. Create a branch for your feature (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the Creative Commons Attribution-NonCommercial 4.0 International License - see the [LICENSE](LICENSE) file for details.   
**ImageMagick's** license can be found [HERE](https://github.com/tiritibambix/ImaGUIck/blob/main/LICENSE).


### Customization

- Modify supported formats: See the `get_available_formats()` function in `app.py`
- Add new processing features: Extend the `build_imagemagick_command()` function in `app.py`

## 📫 Contact

For any questions or suggestions, feel free to:
- Open an issue on GitHub
- Submit a pull request
- Contact the project maintainer

---

Made with ❤️ in Python
