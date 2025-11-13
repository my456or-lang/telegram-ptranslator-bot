# ---------- שלב 1: בחירת סביבת בסיס ----------
FROM python:3.11-slim

# ---------- שלב 2: תיקיית העבודה ----------
WORKDIR /app

# ---------- שלב 3: התקנת רכיבי מערכת ----------
# ffmpeg נדרש רק כדי ש-MoviePy תוכל לקרוא וידאו ולחלץ ממנו אודיו
RUN apt-get update && apt-get install -y ffmpeg && apt-get clean

# ---------- שלב 4: העתקת דרישות והתקנתן ----------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---------- שלב 5: העתקת קבצי האפליקציה ----------
COPY . .

# ---------- שלב 6: הגדרת משתנה סביבה ----------
ENV PORT=8080

# ---------- שלב 7: הפעלת האפליקציה ----------
CMD ["python", "app.py"]
