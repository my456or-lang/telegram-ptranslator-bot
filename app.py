import os
import uuid
import threading
import requests
from flask import Flask, request
from moviepy.editor import VideoFileClip, CompositeVideoClip, ImageClip
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# התקנת גופנים (רק לוודא)
os.system("apt-get update && apt-get install -y fonts-dejavu-core fonts-noto-cjk fonts-freefont-ttf")

# ======================================================
# כתוביות בעברית
# ======================================================
def add_hebrew_subtitles(input_path, output_path, text):
    clip = VideoFileClip(input_path)

    # גופן תומך עברית
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    if not os.path.exists(font_path):
        font_path = "/usr/share/fonts/truetype/freefont/FreeSans.ttf"

    text = text.strip()

    # יצירת שם ייחודי לקובץ PNG
    temp_img = f"subtitle_{uuid.uuid4().hex}.png"

    font = ImageFont.truetype(font_path, 60)
    dummy_img = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(dummy_img)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    img = Image.new("RGBA", (text_w + 80, text_h + 50), (0, 0, 0, 160))
    draw = ImageDraw.Draw(img)
    draw.text((40, 20), text, font=font, fill=(255, 255, 255, 255))
    img.save(temp_img)

    subtitle_clip = (
        ImageClip(temp_img)
        .set_duration(clip.duration)
        .set_position(("center", clip.h - 150))
    )

    final = CompositeVideoClip([clip, subtitle_clip])
    final.write_videofile(
        output_path,
        codec="libx264",
        audio_codec="aac",
        temp_audiofile=None,
        remove_temp=False,
        threads=2,
        fps=clip.fps
    )

    os.remove(temp_img)

# ======================================================
# שליחת הודעה למשתמש
# ======================================================
def send_message(chat_id, text):
    requests.post(f"{BASE_URL}/sendMessage", json={"chat_id": chat_id, "text": text})

def send_video(chat_id, video_path, caption=None):
    with open(video_path, "rb") as video:
        requests.post(f"{BASE_URL}/sendVideo", data={"chat_id": chat_id, "caption": caption}, files={"video": video})

# ======================================================
# עיבוד הסרטון ברקע
# ======================================================
def process_video(chat_id, file_id):
    try:
        send_message(chat_id, "⏳ מעבד את הסרטון שלך... זה עשוי לקחת דקה-שתיים.")
        file_info = requests.get(f"{BASE_URL}/getFile?file_id={file_id}").json()

        if "result" not in file_info:
            send_message(chat_id, "❌ שגיאה: לא ניתן לגשת לקובץ הסרטון.")
            return

        file_path = file_info["result"]["file_path"]
        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"

        input_video = f"input_{uuid.uuid4().hex}.mp4"
        output_video = f"output_{uuid.uuid4().hex}.mp4"

        # הורדת הסרטון
        with open(input_video, "wb") as f:
            f.write(requests.get(file_url).content)

        # הוספת כתוביות
        add_hebrew_subtitles(input_video, output_video, "שלום עולם 🌍")

        # שליחה חזרה
        send_video(chat_id, output_video, "🎬 הנה הסרטון שלך עם כתוביות בעברית!")

    except Exception as e:
        send_message(chat_id, f"❌ שגיאה בעיבוד הסרטון: {e}")

    finally:
        for path in [input_video, output_video]:
            if os.path.exists(path):
                os.remove(path)

# ======================================================
# Webhook
# ======================================================
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    if not data or "message" not in data:
        return "ok"

    message = data["message"]
    chat_id = message["chat"]["id"]

    # התחלה
    if "text" in message and message["text"] == "/start":
        send_message(chat_id, "👋 היי! שלח לי סרטון ואני אוסיף לו כתוביות בעברית!")
        return "ok"

    # קבלת סרטון
    if "video" in message:
        file_id = message["video"]["file_id"]
        threading.Thread(target=process_video, args=(chat_id, file_id)).start()
        return "ok"

    return "ok"

# ======================================================
@app.route("/")
def index():
    return "✅ Telegram Hebrew Subtitle Bot is running!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
