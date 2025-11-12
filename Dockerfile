FROM python:3.11-slim

# התקנת כל התלויות הדרושות ל-moviepy (כולל ffmpeg, ImageMagick, fonts, וכו')
RUN apt-get update && apt-get install -y \
    ffmpeg \
    imagemagick \
    libx11-6 \
    libsm6 \
    libxext6 \
    libgl1 \
    fonts-dejavu-core \
    curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 10000

CMD ["python", "app.py"]
