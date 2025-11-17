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

# יצירת תיקיית גופנים
RUN mkdir -p /app/fonts

# העתקת הגופן העברי
COPY fonts/NotoSansHebrew-VariableFont_wdth,wght.ttf /app/fonts/

# העתקה והתקנת requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# העתקת כל הקבצים
COPY . .

# בדיקה שהגופן קיים
RUN ls -la /app/fonts/

# יציאת Flask
EXPOSE 10000

# הרצת האפליקציה
CMD ["python", "app.py"]
