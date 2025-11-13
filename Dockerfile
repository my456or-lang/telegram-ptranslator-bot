# שלב 1: בחירת תמונת בסיס
FROM python:3.11-slim

# שלב 2: הגדרת ספריית העבודה
WORKDIR /app

# שלב 3: התקנת ffmpeg (נדרש ל-MoviePy)
RUN apt-get update && apt-get install -y ffmpeg && apt-get clean

# שלב 4: העתקת קובץ דרישות
COPY requirements.txt .

# שלב 5: התקנת הדרישות
RUN pip install --no-cache-dir -r requirements.txt

# שלב 6: העתקת קבצי האפליקציה
COPY . .

# שלב 7: חשיפת פורט
EXPOSE 8080

# שלב 8: הרצת האפליקציה
CMD ["python", "app.py"]
