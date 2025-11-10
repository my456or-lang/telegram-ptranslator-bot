FROM python:3.11-slim

# הגדרת משתני סביבה
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    IMAGEMAGICK_BINARY=/usr/bin/convert

# התקנת חבילות מערכת
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    imagemagick \
    fonts-dejavu \
    fonts-dejavu-core \
    fonts-dejavu-extra \
    fonts-liberation \
    fonts-liberation2 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libglib2.0-0 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# תיקון policy של ImageMagick - חשוב מאוד!
# מאפשר לMoviePy לעבוד עם ImageMagick
RUN if [ -f /etc/ImageMagick-6/policy.xml ]; then \
        sed -i 's/<policy domain="path" rights="none" pattern="@\*"/<policy domain="path" rights="read|write" pattern="@*"/g' /etc/ImageMagick-6/policy.xml && \
        sed -i 's/<policy domain="coder" rights="none" pattern="PDF"/<policy domain="coder" rights="read|write" pattern="PDF"/g' /etc/ImageMagick-6/policy.xml && \
        sed -i 's/<policy domain="coder" rights="none" pattern="LABEL"/<policy domain="coder" rights="read|write" pattern="LABEL"/g' /etc/ImageMagick-6/policy.xml; \
    fi

# יצירת תיקיית עבודה
WORKDIR /app

# יצירת תיקיית temp עם הרשאות מלאות (חשוב ל-MoviePy)
RUN mkdir -p /tmp/moviepy && chmod 777 /tmp/moviepy

# העתקה והתקנת requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# העתקת קבצי האפליקציה
COPY app.py .

# יצירת משתמש לא-root (אבטחה)
RUN useradd -m -u 1000 botuser && \
    chown -R botuser:botuser /app /tmp/moviepy

# החלפה למשתמש לא-root
USER botuser

# בריאות check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:10000/health', timeout=5)" || exit 1

# יציאת Flask
EXPOSE 10000

# הרצת האפליקציה
CMD ["python", "-u", "app.py"]
