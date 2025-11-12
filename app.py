import os
import tempfile
import numpy as np
from moviepy.editor import VideoFileClip, CompositeVideoClip, ImageClip
from PIL import Image, ImageDraw, ImageFont
from flask import Flask
import telebot
import requests
from bidi.algorithm import get_display  # כיוון טקסט עברי תקין
import textwrap
from googletrans import Translator

# ===== משתני סביבה =====
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
PORT = int(os.getenv("PORT", 10000))

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
app = Flask(__name__)
translator = Translator()


# ===== פונקציות עזר =====
def get_font(size=36):
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    return ImageFont.truetype(font_path, size)


def prepare_hebrew_text(text: str) -> str:
    """הפיכת עברית לכיוון הנכון (מימין לשמאל)"""
    return get_display(text)


def wrap_text(text, font, max_width, draw):
    """פיצול שורה ארוכה למספר שורות"""
    lines = []
    words = text.split()
    line = ""
    for word in words:
        test_line = word + " " + line  # עבור עברית, מוסיפים מימין
        w, _ = draw.textsize(test_line, font=font)
        if w <= max_width:
            line = test_line
        else:
            lines.append(line.strip())
            line = word
    if line:
        lines.append(line.strip())
    return lines


def make_text_image(text, width, height):
    """יצירת תמונה עם כתוביות עבריות ורקע שחור אטום"""
    img = Image.new("RGB", (width, height), (0, 0, 0))  # רקע שחור מלא
    draw = ImageDraw.Draw(img)

    hebrew_text = prepare_hebrew_text(text)
    font = get_font(size=38)
    max_text_width = int(width * 0.9)
    lines = wrap_text(hebrew_text, font, max_text_width, draw)

    line_height = 50
    total_height = len(lines) * line_height
    y_start = (height - total_height) // 2

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        text_width = bbox[2] - bbox[0]
        x = (width - text_width) // 2
        y = y_start + i * line_height

        # קונטור שחור סביב הטקסט
        outline_range = 2
        for ox in range(-outline_range, outline_range + 1):
            for oy in range(-outline_range, outline_range + 1):
                draw.text((x + ox, y + oy), line, font=font, fill=(0, 0, 0))
        # טקסט לבן
        draw.text((x, y), line, font=font, fill=(255, 255, 255))

    return np.array(img, dtype=np.uint8)


def create_hebrew_subtitle_clip(text, start, duration, video_size):
    width, height = video_size
    subtitle_height = 150
    arr = make_text_image(text, width, subtitle_height)
    txt_clip = ImageClip(arr).set_duration(duration).set_start(start)
    txt_clip = txt_clip.set_position(("center", height - subtitle_height - 30))
    return txt_clip


def transcribe_with_groq(video_path):
    """פונקציית דמה לתמלול (יש להחליף ב-Groq Whisper אמיתי)"""
    # כאן תשתמש ב-Groq API בפועל.
    return [
        {"start": 0, "end": 3, "text": "Hello everyone"},
        {"start": 3, "end": 6, "text": "This is a test video"},
        {"start": 6, "end": 9, "text": "Let's see how it works"},
    ]


# ===== Flask Health Check =====
@app.route("/health")
def health():
    return "OK"


# ===== Telegram Bot =====
@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(message, "ברוך הבא 🎬\nשלח לי סרטון באנגלית ואני אחזיר לך אותו עם כתוביות בעברית!")


@bot.message_handler(content_types=["video"])
def handle_video(message):
    bot.reply_to(message, "📥 מוריד את הסרטון שלך...")

    file_info = bot.get_file(message.video.file_id)
    url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_info.file_path}"

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(requests.get(url).content)
        input_path = f.name

    # תמלול
    transcript = transcribe_with_groq(input_path)

    # תרגום לעברית
    hebrew_lines = []
    for seg in transcript:
        translated = translator.translate(seg["text"], dest="he").text
        hebrew_lines.append({
            "start": seg["start"],
            "duration": seg["end"] - seg["start"],
            "text": translated
        })

    # יצירת סרטון עם כתוביות
    video = VideoFileClip(input_path)
    subtitles = [
        create_hebrew_subtitle_clip(s["text"], s["start"], s["duration"], video.size)
        for s in hebrew_lines
    ]

    final = CompositeVideoClip([video] + subtitles)
    output_path = tempfile.mktemp(suffix=".mp4")
    final.write_videofile(output_path, codec="libx264", audio_codec="aac")

    bot.reply_to(message, "🎞️ מעלה את הסרטון המתורגם...")

    with open(output_path, "rb") as f:
        bot.send_video(message.chat.id, f, caption="🎬 הנה הסרטון שלך עם כתוביות בעברית!")

    os.remove(input_path)
    os.remove(output_path)


if __name__ == "__main__":
    import threading
    threading.Thread(target=lambda: bot.polling(none_stop=True)).start()
    app.run(host="0.0.0.0", port=PORT)
