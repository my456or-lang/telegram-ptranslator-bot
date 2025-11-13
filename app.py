import os
import requests
from flask import Flask, request
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
from deep_translator import GoogleTranslator
from openai import OpenAI

app = Flask(__name__)

# 🎯 יצירת לקוח OpenAI לפי מפתח מהסביבה
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# 🎯 טוקן של טלגרם
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# 🔠 גופן עברי ברירת מחדל (יתקין אוטומטית ב-Render)
os.system("apt-get update && apt-get install -y fonts-dejavu-core")

# ======================================================
# 🧠 פונקציה שמוסיפה כתוביות בעברית (כיוון תקין)
# ======================================================
def add_hebrew_subtitles(input_path, output_path, text):
    clip = VideoFileClip(input_path)
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

    # הפוך טקסט כי moviepy לא תומך RTL
    text = text[::-1]

    txt_clip = TextClip(
        text,
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
# 📨 שליחת הודעה לטלגרם
# ======================================================
def send_message(chat_id, text):
    requests.post(f"{BASE_URL}/sendMessage", json={"chat_id": chat_id, "text": text})

# ======================================================
# 🎥 שליחת סרטון לטלגרם
# ======================================================
def send_video(chat_id, video_path, caption=None):
    with open(video_path, "rb") as video:
        requests.post(f"{BASE_URL}/sendVideo", data={"chat_id": chat_id, "caption": caption}, files={"video": video})

# ======================================================
# 📬 Webhook — הנקודה שטלגרם שולח אליה עדכונים
# ======================================================
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)

    if "message" not in data:
        return "ok"

    message = data["message"]
    chat_id = message["chat"]["id"]

    # 🟢 /start
    if "text" in message and message["text"] == "/start":
        send_message(chat_id, "👋 שלח לי סרטון באנגלית ואוסיף לו כתוביות בעברית 🎧📜")
        return "ok"

    # 🎬 סרטון התקבל
    if "video" in message:
        send_message(chat_id, "🎬 מוריד את הסרטון שלך...")

        try:
            file_id = message["video"]["file_id"]
            file_info = requests.get(f"{BASE_URL}/getFile?file_id={file_id}").json()
            file_path = file_info["result"]["file_path"]
            file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"

            # הורדת הסרטון
            input_path = "input.mp4"
            with open(input_path, "wb") as f:
                f.write(requests.get(file_url).content)

            send_message(chat_id, "🎧 ממיר את הדיבור לטקסט...")

            # הפעלת Whisper לזיהוי דיבור
            with open(input_path, "rb") as audio_file:
                transcript = client.audio.transcriptions.create(
                    model="gpt-4o-mini-transcribe",
                    file=audio_file
                )

            text = transcript.text.strip()

            # תרגום לעברית
            translated = GoogleTranslator(source="en", target="he").translate(text)

            # הוספת כתוביות
            send_message(chat_id, "✍️ מוסיף כתוביות לעברית...")
            output_path = "output.mp4"
            add_hebrew_subtitles(input_path, output_path, translated)

            # שליחת הסרטון בחזרה
            send_video(chat_id, output_path, "🎬 הנה הסרטון שלך עם כתוביות בעברית!")

        except Exception as e:
            send_message(chat_id, f"❌ שגיאה בעיבוד הסרטון:\n{e}")

        finally:
            for path in ["input.mp4", "output.mp4"]:
                if os.path.exists(path):
                    os.remove(path)

    return "ok"

# ======================================================
# 🧭 דף בית לבדיקה
# ======================================================
@app.route("/")
def index():
    return "✅ Telegram Subtitle Bot is running with OpenAI v1.x"

# ======================================================
# 🚀 הפעלת השרת
# ======================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
