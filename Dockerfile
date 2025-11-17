FROM python:3.11-slim

# התקנת חבילות מערכת
RUN apt-get update && apt-get install -y \
    ffmpeg \
    wget \
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

# יצירת תיקיית גופנים והורדת הגופן העברי
RUN mkdir -p /app/fonts && \
    wget -O /app/fonts/NotoSansHebrew-VariableFont_wdth,wght.ttf \
    "https://github.com/notofonts/hebrew/raw/main/fonts/NotoSansHebrew/googlefonts/variable-ttf/NotoSansHebrew%5Bwdth%2Cwght%5D.ttf" && \
    ls -lh /app/fonts/

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
