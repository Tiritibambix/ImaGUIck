## **Image Resizer GUI with Docker**

This repository contains a Python-based graphical application for resizing images, built using Tkinter and ImageMagick. The application supports resizing local files, downloading images from URLs, and batch processing.

## **Features**

-   Resize images by dimensions (pixels) or percentage.
-   Batch processing for multiple images.
-   Download images from URLs for resizing.
-   Lightweight GUI with a progress bar.

___

## **Prerequisites**

1.  **Install Docker**  
    Ensure Docker is installed on your system. You can download it from [Docker's official website](https://www.docker.com/).
2.  **X11 Server**  
    On Linux systems, ensure X11 is configured to allow GUI applications inside Docker containers.

___

## **How to Use**

### 1\. **Clone the repository**

```bash
git clone https://github.com/your-username/image-resizer.git
cd image-resizer
```

### 2\. **Build the Docker image**

```bash
docker build -t imagemagicksimplegui .
```

### 3\. **Run the application**

```bash
docker run -it --rm \
    -v $(pwd)/uploads:/app/uploads \
    -v $(pwd)/output:/app/output \
    -p 5000:5000 \
    imagemagicksimplegui
```

#### **Note (for Linux users):**

If you encounter issues with GUI display, run this command to allow X11 connections:
```bash
xhost +local:
```

___

## **Project Structure**

```
image-resizer/
├── Dockerfile         # Instructions to build the Docker image
├── requirements.txt   # Python dependencies
├── app.py             # The main Python application
├── README.md          # Documentation
├── Lisence.md         # Lisence for ImageMagick
└── .gitignore         # Excluded files for version control
```

___

## **License**

This project is licensed under the MIT License.
ImageMagic's license [HERE](https://github.com/tiritibambix/ImageMagickSimpleGUI/blob/main/Lisence.md).
