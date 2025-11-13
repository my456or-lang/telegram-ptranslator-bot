# שלב 1: בסיס
FROM python:3.11-slim

# התקנת תלות מערכת (ffmpeg עבור moviepy)
RUN apt-get update && apt-get install -y ffmpeg && apt-get clean

# העתקת קבצים
WORKDIR /app
COPY . /app

# התקנת חבילות
RUN pip install --no-cache-dir -r requirements.txt

# משתני סביבה
ENV PORT=8080

# הפעלת הבוט
CMD ["python", "app.py"]
