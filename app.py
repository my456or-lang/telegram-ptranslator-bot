import os
import requests
from flask import Flask, request
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
from groq import Groq
from deep_translator import GoogleTranslator
import tempfile

# ======================================================
# ⚙️ הגדרות כלליות
# ======================================================
app = Flask(__name__)

# מפתחות מהסביבה
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

# בדיקה שהמפתחות קיימים
if not TELEGRAM_TOKEN:
    raise ValueError("❌ משתנה הסביבה TELEGRAM_TOKEN לא הוגדר!")
if not GROQ_API_KEY:
    raise ValueError("❌ משתנה הסביבה GROQ_API_KEY לא הוגדר!")

# יצירת חיבור ל-Groq
client = Groq(api_key=GROQ_API_KEY)

# כתובת בסיסית של טלגרם
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# ======================================================
# 🧠 פונקציה: יצירת כתוביות מתורגמות
# ======================================================
def transcribe_and_translate(audio_path):
    """ממיר דיבור לטקסט באנגלית ואז מתרגם לעברית"""
    try:
        with open(audio_path, "rb") as f:
            transcription = client.audio.transcriptions.create(
                file=(audio_path, f.read()),
                model="whisper-large-v3"
            )

        english_text = transcription.text
        hebrew_text = GoogleTranslator(source='auto', target='he').translate(english_text)
        return hebrew_text
    except Exception as e:
        return f"שגיאה בתמלול או תרגום: {e}"

# ======================================================
# ✍️ פונקציה: הוספת כתוביות לסרטון
# ======================================================
def add_subtitles(input_path, output_path, subtitle_text):
    clip = VideoFileClip(input_path)
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

    # הופכים את הכיוון כדי להציג עברית נכון
    subtitle_text = subtitle_text[::-1]

    txt_clip = TextClip(
        subtitle_text,
        fontsize=60,
        color='white',
        font=font_path,
        method='caption',
        size=(clip.w - 100, None),
        align='East'
    )

    txt_clip = txt_clip.set_position(('center', clip.h - 150)).set_duration(clip.duration)
    result = CompositeVideoClip([clip, txt_clip])
    result.write_videofile(output_path, codec="libx264", audio_codec="aac")

# ======================================================
# 💬 שליחת הודעות וסרטונים
# ======================================================
def send_message(chat_id, text):
    requests.post(f"{BASE_URL}/sendMessage", json={"chat_id": chat_id, "text": text})

def send_video(chat_id, video_path, caption=None):
    with open(video_path, "rb") as video:
        requests.post(
            f"{BASE_URL}/sendVideo",
            data={"chat_id": chat_id, "caption": caption},
            files={"video": video}
        )

# ======================================================
# 📬 Webhook — נקודת כניסה מהטלגרם
# ======================================================
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    if not data or "message" not in data:
        return "ok"

    message = data["message"]
    chat_id = message["chat"]["id"]

    # פקודת התחלה
    if "text" in message and message["text"] == "/start":
        send_message(chat_id, "👋 שלח לי סרטון באנגלית ואוסיף לו כתוביות בעברית 🎧📜")
        return "ok"

    # טיפול בסרטון
    if "video" in message:
        send_message(chat_id, "🎬 מוריד את הסרטון שלך...")
        try:
            file_id = message["video"]["file_id"]
            file_info = requests.get(f"{BASE_URL}/getFile?file_id={file_id}").json()
            file_path = file_info["result"]["file_path"]
            file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"

            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as input_file:
                input_file.write(requests.get(file_url).content)
                input_path = input_file.name

            audio_path = input_path.replace(".mp4", ".mp3")
            output_path = input_path.replace(".mp4", "_output.mp4")

            send_message(chat_id, "🎧 ממיר את הדיבור לטקסט...")

            # שליפת כתוביות
            hebrew_text = transcribe_and_translate(audio_path)

            send_message(chat_id, "📝 מוסיף כתוביות לסרטון...")

            add_subtitles(input_path, output_path, hebrew_text)

            send_video(chat_id, output_path, "🎬 הנה הסרטון שלך עם כתוביות בעברית!")

        except Exception as e:
            send_message(chat_id, f"❌ שגיאה בעיבוד הסרטון:\n\n{e}")

    return "ok"

# ======================================================
# 🌍 דף הבית
# ======================================================
@app.route("/")
def index():
    return "✅ Telegram Hebrew Subtitle Bot is running!"

# ======================================================
# 🚀 הרצה
# ======================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
