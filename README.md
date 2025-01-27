<p align="center">
  <img src="https://i.postimg.cc/rFRD78SG/Ima-GUIck-logo-NOWM-50.png" width="400" />
</p>

ImaGUIck is a simple and intuitive web application for batch image processing, providing a user-friendly graphical interface to resize and convert your images.

## ✨ Features

- 🖼️ **Single or Batch Image Processing**:
  - Process individual images
  - Batch process multiple images with ZIP export
  - Clear success/error feedback for each operation
- 📏 **Flexible Resizing Options**:
  - By specific dimensions (width x height)
  - By percentage
  - With or without aspect ratio preservation
- 🔄 **Smart Format Support**:
  - Common formats (JPG, PNG, GIF, etc.)
  - RAW formats (ARW, CR2, CR3, NEF, RAF, RW2, DNG)
  - Modern formats (WEBP, AVIF, HEIC)
  - Animation formats (GIF, WEBP, APNG)
  - Vector formats (SVG, PDF, EPS)
- 🌐 **Image Import from URL**
- 📦 **Enhanced Batch Processing**:
  - ZIP export with organized structure
  - Detailed processing status for each image
  - Error handling with specific feedback
- 🎨 **Advanced Image Analysis**:
  - Automatic transparency detection
  - Photo vs. graphic type detection
  - Format-specific optimizations
- 💾 **Smart Format Recommendations**:
  - Context-aware format suggestions
  - Quality-preserving options (PNG, DNG)
  - Format-specific optimizations
  - Support for modern compression formats
- 🔍 **Automatic Image Type Analysis**
- 🔍 **Intelligent Format Recommendations**

## 🚀 Installation

### Prerequisites

- Python 3.9+
- [`ImageMagick 7.1.1-41`](https://github.com/ImageMagick/ImageMagick/releases/tag/7.1.1-41) or newer
- ExifTool
- Docker (optional, for containerized deployment)

### Local Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/tiritibambix/ImaGUIck.git
   cd ImaGUIck
   ```

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Ensure ImageMagick and ExifTool are properly installed and accessible from your PATH.

4. Run the application:
   ```bash
   python app.py
   ```

   The application will be available at `http://localhost:5000`

> **Note**: For Windows users, make sure to add ImageMagick to your system's PATH during installation.

### Installation with Docker (supports amd64 and arm64)

1. Clone the repository

   ```bash
   git clone https://github.com/tiritibambix/ImaGUIck.git
   cd ImaGUIck
   ```

2. Build the Docker image

   ```bash
   docker build -t imaguick .
   ```

3. Run the application

   ```bash
   docker run -it --rm \
       -v $(pwd)/uploads:/app/uploads \
       -v $(pwd)/output:/app/output \
       -p 5000:5000 \
       imaguick
   ```
 
#### Alternatively, you can use docker-compose to run the application:

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

### Automatic Cleanup

- Uploaded and processed files are automatically cleaned up after 48 hours
- To manually trigger an immediate cleanup:
  ```bash
  docker exec <container_name> /app/cleanup.sh
  ```
  Replace `<container_name>` with your container name (e.g., `imaguick`)

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
├── Dockerfile                  # Container configuration and build instructions
├── LICENSE                     # Project and ImageMagick licenses
├── README.md                   # Project documentation
├── TODO.md                     # Development roadmap and planned features
├── app.py                      # Main application logic and routes
├── cleanup.py                  # Automatic file cleanup script
├── cleanup.sh                  # Shell script for manual cleanup
├── docker-compose.yml          # Docker Compose configuration
├── requirements.txt            # Python package dependencies
├── start.sh                    # Container startup script
├── templates                   # HTML templates for the web interface
|     ├── base.html             # Base template with common styling
|     ├── index.html            # Main upload and import page
|     ├── resize.html           # Single image processing options
|     ├── resize_batch.html     # Batch processing configuration
|     ├── result.html           # Success/Error feedback display
```

The application follows a clean and modular structure:
- Core application files at the root level for easy deployment
- Separate cleanup scripts for automated and manual file management
- Containerization support with Docker and Docker Compose
- Modular template system for the web interface

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
