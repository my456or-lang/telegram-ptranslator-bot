from flask import Flask, request
import telebot
from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip
from deep_translator import GoogleTranslator
from bidi.algorithm import get_display
import arabic_reshaper
from PIL import Image, ImageDraw, ImageFont
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
        chat_id = message.chat.id
        bot.send_message(chat_id, "⏳ מעבד את הסרטון ומוסיף כתוביות...")

        file_info = bot.get_file(message.video.file_id)
        file_path = file_info.file_path
        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"

        input_path = "input.mp4"
        output_path = "output.mp4"

        os.system(f"curl -L '{file_url}' -o {input_path}")

        # טקסט לדוגמה
        text = "Hello world"

        # תרגום לעברית
        translated = GoogleTranslator(source='auto', target='iw').translate(text)
        reshaped = arabic_reshaper.reshape(translated)
        bidi_text = get_display(reshaped)

        # פתיחת הסרטון
        clip = VideoFileClip(input_path)

        # === יצירת שכבת טקסט עם גופן שתומך בעברית ===
        def create_text_image(text, size=(clip.w, 100), fontsize=45):
            img = Image.new("RGBA", size, (255, 255, 255, 255))
            draw = ImageDraw.Draw(img)

            # שימוש בגופן DejaVuSans שמובנה בלינוקס
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", fontsize, encoding="utf-8")
            except:
                font = ImageFont.load_default()

            # ציור הטקסט במרכז
            text_bbox = draw.textbbox((0, 0), text, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
            x = (size[0] - text_width) / 2
            y = (size[1] - text_height) / 2
            draw.text((x, y), text, fill="black", font=font)
            return np.array(img)

        # יצירת תמונת טקסט וקליפ
        txt_img = create_text_image(bidi_text)
        text_overlay = (ImageClip(txt_img)
                        .set_duration(clip.duration)
                        .set_position(('center', 'bottom')))

        final = CompositeVideoClip([clip, text_overlay])
        final.write_videofile(output_path, codec='libx264', audio_codec='aac')

        with open(output_path, 'rb') as video:
            bot.send_video(chat_id, video, caption="🎬 הנה הסרטון המתורגם שלך!")

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
