import os
import uuid
import threading
import requests
from flask import Flask, request
from moviepy.editor import VideoFileClip, CompositeVideoClip, ImageClip
from PIL import Image, ImageDraw, ImageFont
import openai

# -------------------------------
# הגדרות כלליות
# -------------------------------
app = Flask(__name__)
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
openai.api_key = os.environ.get("OPENAI_API_KEY")

os.system("apt-get update && apt-get install -y fonts-dejavu-core fonts-noto-cjk fonts-freefont-ttf")

lock = threading.Lock()
is_busy = False

# ======================================================
# 🎙️ זיהוי דיבור מאודיו (Whisper)
# ======================================================
def transcribe_audio(audio_path):
    with open(audio_path, "rb") as audio_file:
        transcript = openai.Audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="text"
        )
    return transcript

# ======================================================
# 🌍 תרגום מאנגלית לעברית
# ======================================================
def translate_to_hebrew(text):
    response = openai.Chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "אתה מתרגם טקסטים מאנגלית לעברית באופן טבעי וברור."},
            {"role": "user", "content": text}
        ]
    )
    return response.choices[0].message.content.strip()

# ======================================================
# 🧾 הוספת כתוביות בעברית
# ======================================================
def add_hebrew_subtitles(input_path, output_path, text):
    clip = VideoFileClip(input_path)

    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    if not os.path.exists(font_path):
        font_path = "/usr/share/fonts/truetype/freefont/FreeSans.ttf"

    text = text.strip()
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
        remove_temp=False,
        threads=2,
        fps=clip.fps
    )

    os.remove(temp_img)

# ======================================================
# 📤 שליחת הודעה / סרטון
# ======================================================
def send_message(chat_id, text):
    requests.post(f"{BASE_URL}/sendMessage", json={"chat_id": chat_id, "text": text})

def send_video(chat_id, video_path, caption=None):
    with open(video_path, "rb") as video:
        requests.post(f"{BASE_URL}/sendVideo", data={"chat_id": chat_id, "caption": caption}, files={"video": video})

# ======================================================
# 🎞️ עיבוד הסרטון (עם תרגום)
# ======================================================
def process_video(chat_id, file_id):
    global is_busy

    with lock:
        if is_busy:
            send_message(chat_id, "🕒 אני כרגע עסוק בעיבוד סרטון אחר. נסה שוב בעוד כמה דקות 🙏")
            return
        is_busy = True

    try:
        send_message(chat_id, "🎬 מוריד את הסרטון שלך...")
        file_info = requests.get(f"{BASE_URL}/getFile?file_id={file_id}").json()

        if "result" not in file_info:
            send_message(chat_id, "❌ שגיאה: לא ניתן לגשת לקובץ הסרטון.")
            return

        file_path = file_info["result"]["file_path"]
        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"

        input_video = f"input_{uuid.uuid4().hex}.mp4"
        output_video = f"output_{uuid.uuid4().hex}.mp4"
        audio_path = f"audio_{uuid.uuid4().hex}.mp3"

        with open(input_video, "wb") as f:
            f.write(requests.get(file_url).content)

        # חילוץ אודיו
        clip = VideoFileClip(input_video)
        clip.audio.write_audiofile(audio_path)

        send_message(chat_id, "🎧 ממיר את הדיבור לטקסט...")
        english_text = transcribe_audio(audio_path)

        send_message(chat_id, "🌍 מתרגם לעברית...")
        hebrew_text = translate_to_hebrew(english_text)

        send_message(chat_id, f"📝 טקסט מתורגם: {hebrew_text[:200]}...")

        add_hebrew_subtitles(input_video, output_video, hebrew_text)
        send_video(chat_id, output_video, "✅ הנה הסרטון שלך עם כתוביות בעברית!")

    except Exception as e:
        send_message(chat_id, f"❌ שגיאה בעיבוד הסרטון: {e}")

    finally:
        for path in [input_video, output_video, audio_path]:
            if os.path.exists(path):
                os.remove(path)
        is_busy = False

# ======================================================
# 📬 Webhook
# ======================================================
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    if not data or "message" not in data:
        return "ok"

    message = data["message"]
    chat_id = message["chat"]["id"]

    if "text" in message and message["text"] == "/start":
        send_message(chat_id, "👋 שלח לי סרטון באנגלית ואוסיף לו כתוביות בעברית 🎧📜")
        return "ok"

    if "video" in message:
        file_id = message["video"]["file_id"]
        threading.Thread(target=process_video, args=(chat_id, file_id)).start()
        return "ok"

    return "ok"

# ======================================================
@app.route("/")
def index():
    return "✅ Telegram Hebrew Subtitle Bot is running with translation!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
