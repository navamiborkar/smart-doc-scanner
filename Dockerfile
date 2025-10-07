# Use a lightweight official Python image
FROM python:3.11-slim

# Install Tesseract and poppler (for PDFs)
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Copy all project files into the container
COPY . /app

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port 5000 for Flask
EXPOSE 5000

# Run the app with Gunicorn (production server)
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:5000"]
