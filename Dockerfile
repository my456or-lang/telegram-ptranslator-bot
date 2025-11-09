FROM python:3.11-slim

# התקנת חבילות מערכת
RUN apt-get update && apt-get install -y \
    ffmpeg \
    fonts-dejavu \
    fonts-dejavu-core \
    fonts-liberation \
    fonts-liberation2 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# יצירת תיקיית עבודה
WORKDIR /app

# העתקה והתקנת requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# העתקת כל הקבצים
COPY . .

# יציאת Flask
EXPOSE 10000

# הרצת האפליקציה
CMD ["python", "app.py"]
