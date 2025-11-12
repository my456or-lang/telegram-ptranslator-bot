# בסיס של פייתון
FROM python:3.11-slim

# התקנת ffmpeg ו־curl
RUN apt-get update && apt-get install -y ffmpeg curl && rm -rf /var/lib/apt/lists/*

# הגדרת סביבת עבודה
WORKDIR /app

# העתקת כל הקבצים
COPY . .

# התקנת תלויות
RUN pip install --no-cache-dir -r requirements.txt

# פתיחת פורט
EXPOSE 10000

# הפעלת השרת
CMD ["python", "app.py"]
