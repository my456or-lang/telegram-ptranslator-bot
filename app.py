import os
import tempfile
import requests
from flask import Flask, request
from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import arabic_reshaper
from bidi.algorithm import get_display

# הגדרות Flask
app = Flask(__name__)

# טוקן של הבוט מהסביבה
BOT_TOKEN = os.getenv("BOT_TOKEN")
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# 🟢 פונקציה ליצירת תמונת טקסט בעברית
def create_text_image(text, size=(720, 100), font_size=48):
    img = Image.new("RGB", size, color="white")

    # טעינת גופן תומך עברית
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except:
        font = ImageFont.load_default()

    draw = ImageDraw.Draw(img)

    # עיבוד טקסט עברי
    reshaped_text = arabic_reshaper.reshape(text)
    bidi_text = get_display(reshaped_text)

    # חישוב מיקום לימין
    bbox = draw.textbbox((0, 0), bidi_text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = size[0] - text_width - 20
    y = (size[1] - text_height) / 2

    draw.text((x, y), bidi_text, fill="black", font=font)
    return np.array(img)


# 🟢 פונקציה ליצירת סרטון עם כתוביות בעברית
def process_video(video_path, translated_text):
    clip = VideoFileClip(video_path)

    # יצירת כיתוב עברי מתוקן
    txt_img = create_text_image(translated_text, size=(clip.w, 100))
    txt_clip = ImageClip(txt_img).set_duration(clip.duration).set_position(("center", "bottom"))

    # שילוב הסרטון עם הכיתוב
    final = CompositeVideoClip([clip, txt_clip])

    # שמירת הסרטון הסופי
    output_path = os.path.join(tempfile.gettempdir(), "translated.mp4")
    final.write_videofile(output_path, codec="libx264", audio_codec="aac")

    clip.close()
    final.close()
    return output_path


# 🟢 שליחת הודעה
def send_message(chat_id, text):
    url = f"{BASE_URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    requests.post(url, json=payload)


# 🟢 שליחת סרטון
def send_video(chat_id, video_path, caption="🎬 הנה הסרטון המתורגם שלך!"):
    url = f"{BASE_URL}/sendVideo"
    with open(video_path, "rb") as video:
        files = {"video": video}
        data = {"chat_id": chat_id, "caption": caption}
        requests.post(url, data=data, files=files)


# 🟢 הנתיב הראשי לבדיקה
@app.route("/")
def home():
    return "✅ הבוט פעיל ועובד!"


# 🟢 וובהוק – כאן מטפלות הבקשות מהטלגרם
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()

    if "message" not in data:
        return "No message", 200

    message = data["message"]
    chat_id = message["chat"]["id"]

    # אם התקבל וידאו
    if "video" in message:
        file_id = message["video"]["file_id"]
        send_message(chat_id, "⏳ מעבד את הסרטון שלך, זה ייקח רגע...")

        # שליפת קובץ מהטלגרם
        file_info = requests.get(f"{BASE_URL}/getFile?file_id={file_id}").json()
        file_path = file_info["result"]["file_path"]
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"

        # שמירה זמנית
        local_video = os.path.join(tempfile.gettempdir(), "input.mp4")
        with open(local_video, "wb") as f:
            f.write(requests.get(file_url).content)

        try:
            # כאן שים את הטקסט שאתה רוצה שיופיע
            translated_text = "שלום עולם"

            output_video = process_video(local_video, translated_text)
            send_video(chat_id, output_video)

        except Exception as e:
            send_message(chat_id, f"❌ שגיאה בעיבוד הסרטון: {e}")
        finally:
            if os.path.exists(local_video):
                os.remove(local_video)

    else:
        send_message(chat_id, "שלח לי סרטון כדי שאתרגם אותו 🎥")

    return "OK", 200


# 🟢 הפעלת השרת
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
