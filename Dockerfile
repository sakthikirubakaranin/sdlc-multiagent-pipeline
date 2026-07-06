FROM python:3.11-slim

# System deps (tesseract for OCR, ffmpeg for audio/video)
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    ffmpeg \
    libmagic1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Create output dirs
RUN mkdir -p outputs/requirements outputs/architecture outputs/code \
             outputs/tests outputs/docs outputs/deployments outputs/security

EXPOSE 8000 8501

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
