# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies (less likely to change often)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    tesseract-ocr=5.3.0-2 \
    libgl1-mesa-glx=22.3.6-1+deb12u1 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy only the requirements file first to leverage caching
COPY requirements.txt /app/requirements.txt

# Install Python dependencies (caches this layer if requirements haven't changed)
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application files (frequently updated)
COPY . /app

# Set appropriate permissions for the app directory and subdirectories
RUN chmod -R 755 /app

# Expose the application port
EXPOSE 8000

# Run the command to start the server
CMD ["uvicorn", "invoice_data_processing.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
