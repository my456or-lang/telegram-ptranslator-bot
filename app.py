import os
import requests
from flask import Flask, request
from moviepy.editor import VideoFileClip, CompositeVideoClip, ImageClip
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# ======================================================
# 🧠 פונקציה שמוסיפה כתוביות בעברית תקינה (בלי הפוך, בלי ריבועים)
# ======================================================
def add_hebrew_subtitles(input_path, output_path, text):
    clip = VideoFileClip(input_path)

    # 🔹 התקנת גופן עברי אם אין
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    if not os.path.exists(font_path):
        os.system("apt-get update && apt-get install -y fonts-noto-cjk fonts-noto-color-emoji fonts-noto-core fonts-freefont-ttf")
        font_path = "/usr/share/fonts/truetype/freefont/FreeSans.ttf"

    # 🔹 עדיף גופן עברי נורמלי (אם יש בשרת)
    hebrew_font = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    if os.path.exists("/usr/share/fonts/truetype/freefont/FreeSans.ttf"):
        hebrew_font = "/usr/share/fonts/truetype/freefont/FreeSans.ttf"

    font = ImageFont.truetype(hebrew_font, 60)

    # 🟢 לא הופכים את הטקסט!
    text = text.strip()

    # מחשבים את הגודל של הכתובית
    dummy_img = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(dummy_img)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    # יוצרים רקע כהה מאחורי הכתובית
    img = Image.new("RGBA", (text_w + 60, text_h + 40), (0, 0, 0, 160))
    draw = ImageDraw.Draw(img)
    draw.text((30, 20), text, font=font, fill=(255, 255, 255, 255))

    temp_img = "subtitle.png"
    img.save(temp_img)

    subtitle_clip = (
        ImageClip(temp_img)
        .set_duration(clip.duration)
        .set_position(("center", clip.h - 150))
    )

    final = CompositeVideoClip([clip, subtitle_clip])
    final.write_videofile(output_path, codec="libx264", audio_codec="aac")

    os.remove(temp_img)

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
# 📬 Webhook
# ======================================================
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)

    if "message" not in data:
        return "ok"

    message = data["message"]
    chat_id = message["chat"]["id"]

    if "text" in message and message["text"] == "/start":
        send_message(chat_id, "👋 היי! שלח לי סרטון ואני אוסיף לו כתוביות בעברית!")
        return "ok"

    if "video" in message:
        send_message(chat_id, "⏳ מעבד את הסרטון שלך... זה עשוי לקחת דקה-שתיים.")
        try:
            file_id = message["video"]["file_id"]
            file_info = requests.get(f"{BASE_URL}/getFile?file_id={file_id}").json()
            file_path = file_info["result"]["file_path"]
            file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"

            input_video = "input.mp4"
            output_video = "output.mp4"
            with open(input_video, "wb") as f:
                f.write(requests.get(file_url).content)

            add_hebrew_subtitles(input_video, output_video, "שלום עולם 🌍")

            send_video(chat_id, output_video, "🎬 הנה הסרטון שלך עם כתוביות בעברית!")

        except Exception as e:
            send_message(chat_id, f"❌ שגיאה בעיבוד הסרטון: {e}")

        finally:
            for path in ["input.mp4", "output.mp4"]:
                if os.path.exists(path):
                    os.remove(path)

    return "ok"

@app.route("/")
def index():
    return "✅ Telegram Hebrew Subtitle Bot is running!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
