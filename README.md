# ImaGUIck 🖼️

ImaGUIck is a powerful and intuitive web application for batch image processing, providing a user-friendly graphical interface to resize and convert your images.

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
- ImageMagick 7.1.1-41
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

### Installation with Docker

1. Build the image:
   ```bash
   docker build -t imaguick .
   ```

2. Run the container:
   ```bash
   docker run -p 5000:5000 imaguick
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
ImaGUIck/
├── app.py              # Main Flask application
├── Dockerfile          # Docker configuration
├── requirements.txt    # Python dependencies
├── templates/          # HTML templates
│   ├── index.html
│   ├── resize.html
│   └── resize_batch.html
├── uploads/           # Temporary upload folder
└── output/           # Output folder for processed images
```

## 🤝 Contribution

Contributions are welcome! To contribute:

1. Fork the project
2. Create a branch for your feature (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🔧 Advanced Configuration

### Environment Variables

- `UPLOAD_FOLDER`: Folder for uploads (default: 'uploads')
- `OUTPUT_FOLDER`: Folder for processed files (default: 'output')
- `FLASK_ENV`: Flask environment ('development' or 'production')

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
