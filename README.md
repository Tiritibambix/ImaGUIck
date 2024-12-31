<p align="center">
  <img src="https://i.postimg.cc/rFRD78SG/Ima-GUIck-logo-NOWM-50.png" width="400" />
</p>

## **Imaguick: Image Resizer Web Application with Docker**

This repository contains a Python-based web application for resizing images, built using Flask and [`ImageMagick 7.1.1-41`](https://github.com/ImageMagick/ImageMagick/releases/tag/7.1.1-41).

The application supports resizing local files, downloading images from URLs, batch processing, and format conversions. It provides a modern web-based interface with responsive design.

## **Features**

- **Resize Options:**
  - Resize images by dimensions (pixels) with optional aspect ratio preservation.
  - Resize images by percentage.
- **Batch Processing:**
  - Resize multiple images simultaneously.
  - Automatically compress processed images into a ZIP file.
- **URL Support:**
  - Download and resize images from external URLs.
  - Supports complex URLs with query parameters.
- **Format Conversion:**
  - Convert images to different formats (e.g., JPG, PNG, WEBP).
- **Responsive Web Interface:**
  - Accessible on desktop and mobile devices.
  - Modern design using HTML5 and CSS.
- **Optimized Metadata Handling:**
  - Removes unnecessary metadata (e.g., EXIF data) to optimize file size.

---

## **Prerequisites**

1. **Install Docker**  
   Ensure Docker is installed on your system. You can download it from [Docker's official website](https://www.docker.com/).
2. **Web Browser**  
   A modern web browser (e.g., Chrome, Firefox, Edge) is required to access the interface.

---

## **How to Use**

### 1. **Clone the repository**

```bash
git clone https://github.com/tiritibambix/ImaGUIck.git
cd ImaGUIck
```

### 2. **Build the Docker image**

```bash
docker build -t imaguick .
```

### 3. **Run the application**

```bash
docker run -it --rm \
    -v $(pwd)/uploads:/app/uploads \
    -v $(pwd)/output:/app/output \
    -p 5000:5000 \
    imaguick
```

### 4. **Access the Web Interface**

Open your browser and navigate to `http://localhost:5000` to access the application.

---

## **Docker-compose**

Alternatively, you can use docker-compose to run the application:

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

---

## **Usage Instructions**

### Upload Local Files
- Navigate to the homepage and upload one or more images.
- Proceed to the resize options for individual or batch processing.

### Resize Options
- **Resize by Pixels:** Enter width and height. Enable the "Keep Aspect Ratio" checkbox to maintain proportions.
- **Resize by Percentage:** Enter a percentage (1-100) for scaling.

### Download from URLs
- Enter an image URL in the "Download and Upload" section.
- The image will be downloaded and processed.

### Batch Processing
- Select multiple images for batch resizing.
- Results are provided as a downloadable ZIP file.

---

## **Project Structure**

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

---

## **Known Limitations**

- Images hosted on certain servers may require specific headers (e.g., User-Agent) to download successfully.
- Very large images or files may impact performance.

---

## **License**

This work is licensed under a Creative Commons Attribution-NonCommercial 4.0 International License.

You are free to:
- Share — copy and redistribute the material in any medium or format
- Adapt — remix, transform, and build upon the material

Under the following terms:
- Attribution — You must give appropriate credit, provide a link to the license, and indicate if changes were made. You may do so in any reasonable manner, but not in any way that suggests the licensor endorses you or your use.
- NonCommercial — You may not use the material for commercial purposes.

For more information, visit: https://creativecommons.org/licenses/by-nc/4.0/
 
**ImageMagick's** license can be found [HERE](https://github.com/tiritibambix/ImaGUIck/blob/main/LICENSE).
