from flask import Flask, request
import telebot
from moviepy.editor import VideoFileClip, CompositeVideoClip, ImageClip
from deep_translator import GoogleTranslator
from bidi.algorithm import get_display
import arabic_reshaper
import os
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import textwrap

# ==========
# קריאת TOKEN מהסביבה (Render)
# ==========
TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN לא הוגדר במשתני הסביבה!")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# פונקציות עזר ליצירת תמונת כתובית עם PIL
def get_font(size=42):
    # נסה פונט קיים במערכת; DejaVu בדרך כלל מותקן על דוקר בסיסי
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except:
                continue
    return ImageFont.load_default()

def wrap_text_for_width(text, font, max_width, draw):
    # מחלק טקסט לשורות לפי רוחב מקסימלי
    words = text.split()
    lines = []
    cur = ""
    for w in words:
        test = (w + " " + cur).strip()  # RTL-aware order is handled before calling
        bbox = draw.textbbox((0,0), test, font=font)
        width = bbox[2] - bbox[0]
        if width <= max_width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines

def make_subtitle_image(text, width, height, fontsize=42):
    """מחזיר numpy array (H,W,3) של תמונה עם רקע שחור וטקסט לבן עם outline"""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 255))  # שחור אטום
    draw = ImageDraw.Draw(img)
    font = get_font(size=fontsize)

    # טקסט בעברית — כבר עבר reshape + bidi לפני הקריאה
    max_text_w = int(width * 0.9)
    # להלן עטיפת טקסט
    lines = wrap_text_for_width(text, font, max_text_w, draw)

    line_h = int(font.getsize("A")[1] * 1.4)
    total_h = len(lines) * line_h
    y_start = (height - total_h) // 2

    # ציור כל שורה עם outline (קונטור) ואז טקסט לבן
    outline = 2
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0,0), line, font=font)
        text_w = bbox[2] - bbox[0]
        x = (width - text_w) // 2
        y = y_start + i * line_h
        # קונטור שחור סביב הטקסט
        for ox in range(-outline, outline+1):
            for oy in range(-outline, outline+1):
                draw.text((x+ox, y+oy), line, font=font, fill=(0,0,0,255))
        # טקסט לבן מעל
        draw.text((x, y), line, font=font, fill=(255,255,255,255))

    # המרת RGBA -> RGB (moviepy ImageClip יכול לקבל גם RGBA אבל לפשטות נחזיר RGB)
    rgb = Image.new("RGB", img.size, (0,0,0))
    rgb.paste(img, mask=img.split()[3])  # משמר אלפא
    arr = np.array(rgb)
    return arr

# ======================
# פקודת /start – הודעת פתיחה
# ======================
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "היי 👋 שלח לי סרטון (עד ~50MB) ואני אתרגם אותו לעברית!")

# ======================
# טיפול בסרטון שנשלח
# ======================
@bot.message_handler(content_types=['video'])
def handle_video(message):
    try:
        file_info = bot.get_file(message.video.file_id)
        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"
        input_path = "input.mp4"
        # הורדת קובץ
        os.system(f"curl -L '{file_url}' -o {input_path}")

        # כאן צריך להחליף לוגיקה אמיתית של תמלול -> מקבל טקסטים. בינתיים דוגמה:
        raw_text = "Hello world"  # TODO: תחליף בתמלול אמיתי מהאודיו

        # תרגום באמצעות deep_translator (שימוש ב־'iw' לעברית)
        translated = GoogleTranslator(source='auto', target='iw').translate(raw_text)
        reshaped = arabic_reshaper.reshape(translated)
        bidi_text = get_display(reshaped)

        # יצירת תמונת כתובית בגודל וידאו
        clip = VideoFileClip(input_path)
        w, h = clip.size
        subtitle_h = int(h * 0.18)  # גובה איזור הכתוביות
        img_arr = make_subtitle_image(bidi_text, w, subtitle_h, fontsize=max(28, int(subtitle_h*0.28)))

        # ImageClip מתוך numpy array
        subtitle_clip = ImageClip(img_arr).set_duration(clip.duration).set_start(0).set_position(("center", h - subtitle_h - 20))

        final = CompositeVideoClip([clip, subtitle_clip])
        output_path = "output.mp4"
        final.write_videofile(output_path, codec='libx264', audio_codec='aac', threads=2, verbose=False, logger=None)

        # שליחת הסרטון המתורגם
        with open(output_path, 'rb') as video:
            bot.send_video(message.chat.id, video, caption="🎬 הנה הסרטון המתורגם שלך!")

        # ניקוי
        try:
            os.remove(input_path)
        except:
            pass
        try:
            os.remove(output_path)
        except:
            pass

    except Exception as e:
        # שליחת שגיאה נגישה למשתמש
        try:
            bot.reply_to(message, f"❌ שגיאה בעיבוד הסרטון: {e}")
        except:
            pass

# ======================
# ניהול Webhook
# ======================
@app.route('/')
def index():
    return "✅ Translation bot is running!"

@app.route('/webhook', methods=['POST'])
def webhook():
    json_str = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return '', 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
