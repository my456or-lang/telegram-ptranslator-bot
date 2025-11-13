import os
import tempfile
import requests
from flask import Flask, request
from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import arabic_reshaper
from bidi.algorithm import get_display
import telebot

# ----------------
# Config
# ----------------
TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN not set in environment")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)
BASE_TEMP = tempfile.gettempdir()

# ----------------
# Helper: load hebrew-capable font
# ----------------
def get_hebrew_font(size):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()

# ----------------
# Helper: create image with RTL Hebrew text (reshaped + bidi)
# ----------------
def create_text_image_hebrew(text, width, height, fontsize=48, padding=20, bg_color=(255,255,255,255), text_color=(0,0,0,255)):
    """
    Returns a numpy RGB array with RTL Hebrew text drawn right-aligned.
    """
    # reshape + bidi
    try:
        reshaped = arabic_reshaper.reshape(text)
        bidi_text = get_display(reshaped)
    except Exception:
        bidi_text = text  # fallback if something goes wrong

    # create RGBA image
    img = Image.new("RGBA", (width, height), bg_color)
    draw = ImageDraw.Draw(img)
    font = get_hebrew_font(fontsize)

    # measure text bbox for bidi_text
    bbox = draw.textbbox((0,0), bidi_text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    # right-align: x = width - padding - text_w
    x = max(padding, width - padding - text_w)
    y = (height - text_h) // 2

    # optional: draw outline for better contrast (simple 1px)
    outline_color = (0,0,0,255)
    for ox, oy in [(-1,0),(1,0),(0,-1),(0,1)]:
        draw.text((x+ox, y+oy), bidi_text, font=font, fill=outline_color)

    # draw main text
    draw.text((x, y), bidi_text, font=font, fill=text_color)

    # convert to RGB numpy (MoviePy ImageClip works with RGB arrays)
    rgb = Image.new("RGB", img.size, (255,255,255))
    rgb.paste(img, mask=img.split()[3])
    return np.array(rgb)

# ----------------
# Bot handlers
# ----------------
@bot.message_handler(commands=['start'])
def cmd_start(message):
    bot.reply_to(message, "היי 👋 שלח לי סרטון ואני אתרגם אותו לעברית!")

@bot.message_handler(content_types=['video'])
def handle_video(message):
    chat_id = message.chat.id
    bot.send_message(chat_id, "⏳ מעבד את הסרטון ומוסיף כתוביות...")

    try:
        file_info = bot.get_file(message.video.file_id)   # telebot returns object with .file_path
        file_path = file_info.file_path
        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"

        input_file = os.path.join(BASE_TEMP, f"input_{message.message_id}.mp4")
        output_file = os.path.join(BASE_TEMP, f"output_{message.message_id}.mp4")

        # download
        resp = requests.get(file_url, timeout=120)
        resp.raise_for_status()
        with open(input_file, "wb") as f:
            f.write(resp.content)

        # --- HERE: get real text (for now we use placeholder) ---
        # TODO: replace with real transcription result (Groq/Whisper/etc.)
        raw_text = "Hello world"
        # translate to hebrew (if using deep-translator)
        # from deep_translator import GoogleTranslator
        # translated = GoogleTranslator(source='auto', target='iw').translate(raw_text)
        # for now we'll use fixed hebrew to demonstrate RTL:
        translated = "שלום עולם"

        # open video and build subtitle image
        clip = VideoFileClip(input_file)
        w, h = clip.w, clip.h
        subtitle_h = int(h * 0.15) if h>200 else 80
        # create image with proper RTL text
        txt_img = create_text_image_hebrew(translated, width=w, height=subtitle_h, fontsize=max(24, subtitle_h//3), padding=24, bg_color=(255,255,255,255), text_color=(0,0,0,255))

        # ImageClip
        from moviepy.editor import ImageClip, CompositeVideoClip
        subtitle_clip = ImageClip(txt_img).set_duration(clip.duration).set_position(("center", h - subtitle_h - 10))

        final = CompositeVideoClip([clip, subtitle_clip])
        # reduce verbose logs
        final.write_videofile(output_file, codec="libx264", audio_codec="aac", threads=2, verbose=False, logger=None)

        # send result
        with open(output_file, "rb") as f:
            bot.send_video(chat_id, f, caption="🎬 הנה הסרטון המתורגם שלך!")

    except Exception as e:
        bot.send_message(chat_id, f"❌ שגיאה בעיבוד הסרטון: {e}")

    finally:
        # cleanup
        for p in (input_file, output_file):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass

# ----------------
# webhook endpoint for Render (or another host)
# ----------------
@app.route("/webhook", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "", 200

@app.route("/")
def index():
    return "✅ Bot running"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
