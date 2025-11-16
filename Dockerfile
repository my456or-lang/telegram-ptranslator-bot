FROM python:3.11-slim

WORKDIR /app

# התקנת ffmpeg, fontconfig ו־utilities
RUN apt-get update && \
    apt-get install -y ffmpeg fontconfig fonts-dejavu-core && \
    rm -rf /var/lib/apt/lists/*

# העתקת requirements והתקנה
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# העתקת כל הקוד (כולל תיקית fonts אם קיימת)
COPY . .

EXPOSE 8080

CMD ["python", "app.py"]
