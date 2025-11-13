import os
import requests
from flask import Flask, request
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
from deep_translator import GoogleTranslator
from groq import Groq

# 🌍 יצירת אפליקציית Flask
app = Flask(__name__)

# 🧠 מפתח ה־API של Groq מהסביבה
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY)

# 🤖 טוקן של בוט טלגרם
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# ======================================================
# 🎧 פונקציה: הפקת תמלול מהסרטון (באנגלית)
# ======================================================
def transcribe_audio(audio_path):
    with open(audio_path, "rb") as f:
        transcription = client.audio.transcriptions.create(
            file=f,
            model="whisper-large-v3",
            response_format="text"
        )
    return transcription.strip()

# ======================================================
# 🌍 תרגום טקסט לאנגלית → עברית
# ======================================================
def translate_to_hebrew(text):
    return GoogleTranslator(source="en", target="he").translate(text)

# ======================================================
# 🧠 הוספת כתוביות בעברית
# ======================================================
def add_hebrew_subtitles(input_path, output_path, text):
    clip = VideoFileClip(input_path)
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

    # הפוך את סדר האותיות לעברית (MoviePy לא תומך RTL)
    hebrew_text = text[::-1]

    txt_clip = TextClip(
        hebrew_text,
        fontsize=60,
        color="white",
        font=font_path,
        method="caption",
        align="East",
        size=(clip.w - 100, None),
    )

    txt_clip = txt_clip.set_position(("center", clip.h - 150)).set_duration(clip.duration)
    result = CompositeVideoClip([clip, txt_clip])
    result.write_videofile(output_path, codec="libx264", audio_codec="aac")

# ======================================================
# 📩 שליחת הודעה בטלגרם
# ======================================================
def send_message(chat_id, text):
    requests.post(f"{BASE_URL}/sendMessage", json={"chat_id": chat_id, "text": text})

# ======================================================
# 🎥 שליחת סרטון חזרה
# ======================================================
def send_video(chat_id, video_path, caption=None):
    with open(video_path, "rb") as video:
        requests.post(f"{BASE_URL}/sendVideo", data={"chat_id": chat_id, "caption": caption}, files={"video": video})

# ======================================================
# 📬 Webhook — נקודת קליטת הודעות מטלגרם
# ======================================================
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)

    if "message" not in data:
        return "ok"

    message = data["message"]
    chat_id = message["chat"]["id"]

    # 🟢 פקודת /start
    if "text" in message and message["text"] == "/start":
        send_message(chat_id, "👋 שלח לי סרטון באנגלית ואוסיף לו כתוביות בעברית 🎧📜")
        return "ok"

    # 🎬 אם נשלח סרטון
    if "video" in message:
        send_message(chat_id, "🎬 מוריד את הסרטון שלך...")

        try:
            file_id = message["video"]["file_id"]
            file_info = requests.get(f"{BASE_URL}/getFile?file_id={file_id}").json()

            if "result" not in file_info:
                send_message(chat_id, "❌ לא ניתן לגשת לקובץ הסרטון.")
                return "ok"

            file_path = file_info["result"]["file_path"]
            file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"

            # שמירת הסרטון
            input_video = "input.mp4"
            with open(input_video, "wb") as f:
                f.write(requests.get(file_url).content)

            # חילוץ אודיו מהוידאו
            send_message(chat_id, "🎧 ממיר את הדיבור לטקסט...")
            clip = VideoFileClip(input_video)
            audio_path = "audio.wav"
            clip.audio.write_audiofile(audio_path)

            # תמלול + תרגום
            english_text = transcribe_audio(audio_path)
            hebrew_text = translate_to_hebrew(english_text)

            # הוספת כתוביות
            send_message(chat_id, "📝 מוסיף כתוביות בעברית...")
            output_video = "output.mp4"
            add_hebrew_subtitles(input_video, output_video, hebrew_text)

            # שליחת הסרטון המתורגם
            send_video(chat_id, output_video, "🎬 הנה הסרטון שלך עם כתוביות בעברית!")

        except Exception as e:
            send_message(chat_id, f"❌ שגיאה בעיבוד הסרטון:\n\n{e}")

        finally:
            for path in ["input.mp4", "output.mp4", "audio.wav"]:
                if os.path.exists(path):
                    os.remove(path)

    return "ok"

# ======================================================
# 🧭 דף הבית
# ======================================================
@app.route("/")
def index():
    return "✅ Telegram + Groq Hebrew Subtitle Bot is running!"

# ======================================================
# 🚀 הפעלת השרת
# ======================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
