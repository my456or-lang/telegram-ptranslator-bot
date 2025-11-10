FROM python:3.11-slim

# הגדרת משתני סביבה
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    IMAGEMAGICK_BINARY=/usr/bin/convert \
    MAGICK_TEMPORARY_PATH=/tmp

# התקנת חבילות מערכת
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    imagemagick \
    fonts-dejavu \
    fonts-dejavu-core \
    fonts-dejavu-extra \
    fonts-liberation \
    fonts-liberation2 \
    fonts-noto \
    fonts-noto-core \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libglib2.0-0 \
    wget \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# תיקון CRITICAL של ImageMagick policy - הסרת כל המגבלות!
RUN POLICY_FILE="/etc/ImageMagick-6/policy.xml" && \
    if [ -f "$POLICY_FILE" ]; then \
        cp "$POLICY_FILE" "$POLICY_FILE.bak" && \
        sed -i '/<policy domain="path" rights="none"/d' "$POLICY_FILE" && \
        sed -i '/<policy domain="coder" rights="none" pattern="PDF"/d' "$POLICY_FILE" && \
        sed -i '/<policy domain="coder" rights="none" pattern="LABEL"/d' "$POLICY_FILE" && \
        sed -i '/<policy domain="coder" rights="none" pattern="PS"/d' "$POLICY_FILE" && \
        sed -i '/<policy domain="coder" rights="none" pattern="EPS"/d' "$POLICY_FILE" && \
        sed -i 's/<policy domain="resource" name="memory" value=".*"/<policy domain="resource" name="memory" value="2GiB"/g' "$POLICY_FILE" && \
        sed -i 's/<policy domain="resource" name="map" value=".*"/<policy domain="resource" name="map" value="2GiB"/g' "$POLICY_FILE" && \
        sed -i 's/<policy domain="resource" name="disk" value=".*"/<policy domain="resource" name="disk" value="4GiB"/g' "$POLICY_FILE"; \
    fi

# יצירת תיקיית עבודה
WORKDIR /app

# יצירת תיקיות temp עם הרשאות מלאות
RUN mkdir -p /tmp/moviepy /tmp/magick && \
    chmod -R 777 /tmp

# העתקה והתקנת requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# העתקת קבצי האפליקציה
COPY app.py .

# הרשאות לתיקייה
RUN chmod -R 755 /app

# בריאות check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:10000/health || exit 1

# יציאת Flask
EXPOSE 10000

# הרצת האפליקציה
CMD ["python", "-u", "app.py"]
