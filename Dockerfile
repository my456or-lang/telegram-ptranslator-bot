# ------------------------------
# בסיס – Python 3.10 קל ומהיר
# ------------------------------
FROM python:3.10-slim

# ------------------------------
# הגדרות סביבתיות
# ------------------------------
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive

# ------------------------------
# עדכון מערכת והתקנת כלים נדרשים
# ------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-dejavu-core \
    fonts-liberation \
    fonts-freefont-ttf \
    fonts-noto-core \
    fonts-noto-cjk \
    fonts-noto-unhinted \
    fonts-noto-color-emoji \
    fonts-noto-extra \
    wget \
    curl \
    unzip \
    ttf-freefont \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ------------------------------
# התקנת פונט עברי איכותי (Assistant)
# ------------------------------
RUN mkdir -p /usr/share/fonts/truetype/assistant \
    && wget -q https://github.com/google/fonts/raw/main/ofl/assistant/Assistant-Regular.ttf \
       -O /usr/share/fonts/truetype/assistant/Assistant-Regular.ttf \
    && fc-cache -fv

# ------------------------------
# התקנת תלויות פייתון
# ------------------------------
COPY requirements.txt /app/requirements.txt
WORKDIR /app
RUN pip install --no-cache-dir -r requirements.txt

# ------------------------------
# העתקת קבצי האפליקציה
# ------------------------------
COPY . /app

# ------------------------------
# פתיחת פורט Flask
# ------------------------------
EXPOSE 10000

# ------------------------------
# הפעלת האפליקציה
# ------------------------------
CMD ["python", "app.py"]
