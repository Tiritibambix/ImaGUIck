
## **Image Resizer Web Application with Docker**

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
git clone https://github.com/tiritibambix/ImageMagickSimpleGUI.git
cd ImageMagickSimpleGUI
```

### 2. **Build the Docker image**

```bash
docker build -t imagemagicksimplegui .
```

### 3. **Run the application**

```bash
docker run -it --rm \
    -v $(pwd)/uploads:/app/uploads \
    -v $(pwd)/output:/app/output \
    -p 5000:5000 \
    imagemagicksimplegui
```

### 4. **Access the Web Interface**

Open your browser and navigate to `http://localhost:5000` to access the application.

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

## **Docker-compose**

Alternatively, you can use docker-compose to run the application:

```yaml
services:
  imagemagicksimplegui:
    stdin_open: true
    tty: true
    volumes:
      - ./uploads:/app/uploads
      - ./output:/app/output
    ports:
      - 5000:5000
    image: tiritibambix/imagemagicksimplegui:latest
networks: {}
```

---

## **Project Structure**

```
imagemagicksimplegui/
├── Dockerfile         # Instructions to build the Docker image
├── requirements.txt   # Python dependencies
├── app.py             # The main Python application
├── templates/         # HTML templates for the web interface
│   ├── index.html     # Homepage
│   ├── resize.html    # Resize options for individual images
│   ├── resize_batch.html # Batch processing options
├── static/            # Static files (CSS, JS)
├── README.md          # Documentation
├── LICENSE            # License for ImageMagick
└── .gitignore         # Excluded files for version control
```

---

## **Known Limitations**

- Images hosted on certain servers may require specific headers (e.g., User-Agent) to download successfully.
- Very large images or files may impact performance.

---

## **License**

This project is licensed under the MIT License.  
ImageMagick's license can be found [HERE](https://github.com/tiritibambix/ImageMagickSimpleGUI/blob/main/LICENSE).
