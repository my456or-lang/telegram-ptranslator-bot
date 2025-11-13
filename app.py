from flask import Flask, request
import telebot
from moviepy.editor import VideoFileClip
from PIL import Image, ImageDraw, ImageFont
from deep_translator import GoogleTranslator
from bidi.algorithm import get_display
import arabic_reshaper
import numpy as np
import os

# ==========
# קריאת TOKEN מהסביבה (Render)
# ==========
TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN לא הוגדר במשתני הסביבה!")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# ======================
# פקודת /start – הודעת פתיחה
# ======================
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "היי 👋 שלח לי סרטון ואני אתרגם אותו לעברית!")


# ======================
# טיפול בסרטון שנשלח
# ======================
@bot.message_handler(content_types=['video'])
def handle_video(message):
    try:
        # קבלת פרטי הקובץ מה-API של טלגרם
        file_info = bot.get_file(message.video.file_id)
        file_path = file_info.file_path
        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"

        input_path = "input.mp4"
        output_path = "output.mp4"

        # הורדת הסרטון
        os.system(f"curl -L '{file_url}' -o {input_path}")

        # טקסט לדוגמה (בהמשך נחלץ טקסט מהסאונד)
        text = "Hello world"

        # תרגום לעברית
        translated = GoogleTranslator(source='auto', target='iw').translate(text)

        # עיבוד כיווניות וטקסט בעברית
        reshaped = arabic_reshaper.reshape(translated)
        bidi_text = get_display(reshaped)

        # יצירת קליפ
        clip = VideoFileClip(input_path)

        # פונקציה ליצירת תמונת טקסט
        def create_text_image(text, size=(clip.w, 100), fontsize=40):
            img = Image.new("RGBA", size, (255, 255, 255, 255))
            draw = ImageDraw.Draw(img)
            try:
                font = ImageFont.truetype("Arial.ttf", fontsize)
            except:
                font = ImageFont.load_default()

            text_bbox = draw.textbbox((0, 0), text, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
            x = (size[0] - text_width) / 2
            y = (size[1] - text_height) / 2
            draw.text((x, y), text, fill="black", font=font)
            return np.array(img)

        # יצירת תמונת טקסט והפיכתה לקליפ
        txt_img = create_text_image(bidi_text)
        txt_clip = (VideoFileClip(input_path)
                    .fl_image(lambda frame: frame)
                    .set_duration(clip.duration))
        
        # מיזוג הסרטון עם שכבת הטקסט
        from moviepy.editor import ImageClip, CompositeVideoClip
        text_overlay = (ImageClip(txt_img)
                        .set_duration(clip.duration)
                        .set_position(('center', 'bottom')))

        final = CompositeVideoClip([clip, text_overlay])
        final.write_videofile(output_path, codec='libx264', audio_codec='aac')

        # שליחת הסרטון למשתמש
        with open(output_path, 'rb') as video:
            bot.send_video(message.chat.id, video, caption="🎬 הנה הסרטון המתורגם שלך!")

        # ניקוי קבצים
        os.remove(input_path)
        os.remove(output_path)

    except Exception as e:
        bot.reply_to(message, f"❌ שגיאה בעיבוד הסרטון: {e}")


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
