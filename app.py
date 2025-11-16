import os
import threading
import tempfile
import traceback
import subprocess
import requests
from flask import Flask
import telebot
from groq import Groq
from deep_translator import GoogleTranslator
from moviepy.editor import VideoFileClip, CompositeVideoClip, ImageClip
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from bidi.algorithm import get_display
import time
import json

# ---------------------------
# CONFIG / ENV
# ---------------------------
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
PORT = int(os.environ.get("PORT", 8080))

if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN לא מוגדר")
if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY לא מוגדר")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None)
client = Groq(api_key=GROQ_API_KEY)
# deep-translator expects 'iw' mapping for Hebrew in some versions
translator = GoogleTranslator(source="auto", target="iw")

app = Flask(__name__)

@app.route("/")
def home():
    return "Telegram subtitle bot — running ✅"

# ---------------------------
# Helpers: timestamps, RTL, fonts
# ---------------------------
def format_timestamp(seconds: float):
    # returns "HH:MM:SS,mmm"
    ms = int((seconds - int(seconds)) * 1000)
    s = int(seconds)
    hh = s // 3600
    mm = (s % 3600) // 60
    ss = s % 60
    return f"{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}"

def contains_hebrew(text: str) -> bool:
    return any('\u0590' <= ch <= '\u05FF' for ch in text)

def prepare_hebrew_text_for_display(text: str) -> str:
    # For Hebrew: use bidi.get_display (do not apply arabic_reshaper)
    try:
        if contains_hebrew(text):
            return get_display(text)
    except Exception:
        pass
    return text

def find_font_path():
    # Check repo font first
    custom = "fonts/NotoSansHebrew-VariableFont_wdth,wght.ttf"
    if os.path.exists(custom):
        return custom
    # fallback fonts
    for p in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
    ]:
        if os.path.exists(p):
            return p
    return None

# ---------------------------
# Groq transcription
# ---------------------------
def transcribe_with_groq(file_path: str):
    # request verbose_json to receive segments
    with open(file_path, "rb") as f:
        resp = client.audio.transcriptions.create(
            model="whisper-large-v3-turbo",
            file=f,
            response_format="verbose_json"
        )
    # resp may be dict-like
    if isinstance(resp, dict):
        return resp
    try:
        return json.loads(str(resp))
    except Exception:
        return resp

# ---------------------------
# Translate text
# ---------------------------
def translate_text(text: str) -> str:
    try:
        return translator.translate(text)
    except Exception as e:
        # fallback: return original
        return text

# ---------------------------
# Create SRT from segments
# ---------------------------
def create_srt_from_segments(segments, out_path):
    """
    segments: list of dicts with 'start','end','text'
    """
    with open(out_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, start=1):
            start = float(seg.get("start", 0))
            end = float(seg.get("end", start + 2))
            text = str(seg.get("text", "")).strip()
            # Prepare Hebrew display
            text = prepare_hebrew_text_for_display(text)
            f.write(f"{i}\n")
            f.write(f"{format_timestamp(start)} --> {format_timestamp(end)}\n")
            f.write(f"{text}\n\n")

# ---------------------------
# Burn SRT with ffmpeg (fast)
# ---------------------------
def burn_srt_with_ffmpeg(video_path: str, srt_path: str):
    # ffmpeg subtitles filter needs the path escaped properly
    out_path = video_path.replace(".mp4", "_subtitled.mp4")
    # Use -y to overwrite; ensure locales/encoding are fine by forcing UTF-8 SRT
    # We try to include fonts if necessary via ASS style but simple subtitles should work.
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", f"subtitles={srt_path}",
        "-c:a", "copy",
        out_path
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr[:1000]}")
    return out_path

# ---------------------------
# Fallback: burn by rendering per-segment images (always works, slower)
# ---------------------------
def burn_with_moviepy_segments(video_path: str, segments):
    clip = VideoFileClip(video_path)
    w, h = clip.w, clip.h
    subtitle_clips = []
    font_path = find_font_path()
    for seg in segments:
        start = float(seg.get("start", 0))
        end = float(seg.get("end", start + 2))
        text = str(seg.get("text", "")).strip()
        text = prepare_hebrew_text_for_display(text)

        # create image (PIL) sized to video width
        fontsize = max(20, int(w / 36))
        if font_path:
            font = ImageFont.truetype(font_path, fontsize)
        else:
            font = ImageFont.load_default()

        # measure and wrap
        dummy = Image.new("RGBA", (10, 10), (0,0,0,0))
        draw = ImageDraw.Draw(dummy)
        max_width = int(w * 0.92)
        # naive wrap
        words = text.split()
        lines = []
        cur = ""
        for word in words:
            cand = (cur + " " + word).strip() if cur else word
            bbox = draw.textbbox((0,0), cand, font=font, stroke_width=2)
            if bbox[2] - bbox[0] <= max_width:
                cur = cand
            else:
                if cur:
                    lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)

        line_h = draw.textbbox((0,0), "A", font=font)[3] - draw.textbbox((0,0), "A", font=font)[1]
        total_h = line_h * len(lines) + 24
        total_w = max_width
        img = Image.new("RGBA", (int(total_w), int(total_h)), (0,0,0,160))
        d = ImageDraw.Draw(img)
        y = 8
        for ln in lines:
            bbox = d.textbbox((0,0), ln, font=font, stroke_width=2)
            tw = bbox[2] - bbox[0]
            x = img.width - 12 - tw  # right align
            try:
                d.text((x, y), ln, font=font, fill=(255,255,255,255), stroke_width=2, stroke_fill=(0,0,0,255))
            except TypeError:
                # fallback
                for ox,oy in [(-1,0),(1,0),(0,-1),(0,1)]:
                    d.text((x+ox,y+oy), ln, font=font, fill=(0,0,0,255))
                d.text((x,y), ln, font=font, fill=(255,255,255,255))
            y += line_h
        arr = np.array(img)
        ic = ImageClip(arr).set_start(max(0, start)).set_duration(max(0.05, end - start)).set_position(("center", h - img.height - 20))
        subtitle_clips.append(ic)

    final = CompositeVideoClip([clip] + subtitle_clips)
    out_path = video_path.replace(".mp4", "_subtitled.mp4")
    final.write_videofile(out_path, codec="libx264", audio_codec="aac", threads=2, preset="ultrafast", verbose=False)
    clip.close()
    final.close()
    return out_path

# ---------------------------
# Telegram handlers
# ---------------------------
@bot.message_handler(commands=['start'])
def on_start(msg):
    bot.reply_to(msg, "👋 היי! שלח סרטון (מקסימום 5 דקות) ואני אחזיר אותו עם כתוביות בעברית (SRT + וידאו עם כתוביות).")

@bot.message_handler(content_types=['video'])
def handle_video(message):
    chat_id = message.chat.id
    try:
        bot.send_message(chat_id, "🎬 מוריד את הסרטון...")
        file_info = bot.get_file(message.video.file_id)
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
        resp = requests.get(file_url, timeout=120)
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        tmp.write(resp.content)
        tmp.flush()
        tmp.close()

        # quick duration check
        try:
            clip = VideoFileClip(tmp.name)
            duration = clip.duration
            clip.close()
            if duration > 5 * 60 + 5:
                bot.send_message(chat_id, "❌ הסרטון ארוך מדי — המקסימום הוא 5 דקות.")
                os.remove(tmp.name)
                return
        except Exception:
            pass

        bot.send_message(chat_id, "🎧 מתמלל (Groq Whisper)... זה עשוי לקחת זמן קצר...")
        resp_json = transcribe_with_groq(tmp.name)
        # resp_json expected to include 'segments'
        segments = []
        if isinstance(resp_json, dict) and 'segments' in resp_json:
            segments = resp_json['segments']
        else:
            # try attribute access
            segments = getattr(resp_json, 'segments', []) or []

        if not segments:
            # try to get raw text as one segment
            text = resp_json.get('text') if isinstance(resp_json, dict) else str(resp_json)
            segments = [{"start": 0.0, "end":  max(2.0, min(10.0, len(text)/10 + 1)), "text": text}]

        bot.send_message(chat_id, f"🌍 מתרגם {len(segments)} מקטעים לעברית...")
        # translate each segment text
        for seg in segments:
            seg['orig_text'] = seg.get('text', '')
            try:
                seg['text'] = translate_text(seg['orig_text'])
            except Exception:
                seg['text'] = seg.get('orig_text', '')

        # create SRT
        srt_path = tempfile.NamedTemporaryFile(delete=False, suffix=".srt").name
        create_srt_from_segments(segments, srt_path)

        bot.send_document(chat_id, open(srt_path, "rb"))
        bot.send_message(chat_id, "✅ קובץ SRT נשלח. מנסה לשרוף כתוביות לתוך הווידאו (FFmpeg)...")

        # try ffmpeg burn
        try:
            out_video = burn_srt_with_ffmpeg(tmp.name, srt_path)
            bot.send_message(chat_id, "📤 הסרטון מוכן — מעלה אותו עכשיו...")
            with open(out_video, "rb") as f:
                bot.send_video(chat_id, f, caption="✅ הנה הסרטון שלך עם כתוביות (FFmpeg burn).")
            # cleanup
            os.remove(tmp.name)
            os.remove(out_video)
            os.remove(srt_path)
            return
        except Exception as e:
            # ffmpeg failed — fallback
            bot.send_message(chat_id, f"⚠️ FFmpeg נכשל (מעבר לגיבוי). מנסה תהליך גיבוי איטי יותר...\n\n{e}")

        # fallback: burn by MoviePy + PIL segments
        try:
            out_video = burn_with_moviepy_segments(tmp.name, segments)
            bot.send_message(chat_id, "📤 הסרטון מוכן (גיבוי ברינדור). מעלה עכשיו...")
            with open(out_video, "rb") as f:
                bot.send_video(chat_id, f, caption="✅ הנה הסרטון שלך עם כתוביות (fallback).")
        except Exception as e:
            bot.send_message(chat_id, f"❌ נכשל ברינדור הכתוביות: {e}\n{traceback.format_exc()}")

        # cleanup
        try:
            os.remove(tmp.name)
        except:
            pass
        try:
            os.remove(srt_path)
        except:
            pass
        try:
            os.remove(out_video)
        except:
            pass

    except Exception as e:
        bot.send_message(chat_id, f"❌ שגיאה כללית: {e}\n{traceback.format_exc()}")

# ---------------------------
# Run bot + Flask for Render compatibility
# ---------------------------
def run_bot():
    # use polling (ensure no webhook active)
    bot.infinity_polling(timeout=60, long_polling_timeout=60)

if __name__ == "__main__":
    t = threading.Thread(target=run_bot, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=PORT)
