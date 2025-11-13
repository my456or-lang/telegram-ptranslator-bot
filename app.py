from flask import Flask, request
import telebot
from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip
from deep_translator import GoogleTranslator
from bidi.algorithm import get_display
import arabic_reshaper
from PIL import Image, ImageDraw, ImageFont
import os

TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN לא הוגדר במשתני הסביבה!")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "היי 👋 שלח לי סרטון ואני אתרגם אותו לעברית!")

@bot.message_handler(content_types=['video'])
def handle_video(message):
    try:
        file_info = bot.get_file(message.video.file_id)
        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"
        input_path = "input.mp4"
        os.system(f"curl -L '{file_url}' -o {input_path}")

        # טקסט לדוגמה
        text = "Hello world"
        translated = GoogleTranslator(source='auto', target='iw').translate(text)
        reshaped = arabic_reshaper.reshape(translated)
        bidi_text = get_display(reshaped)

        # יצירת תמונת טקסט
        font = ImageFont.truetype("DejaVuSans.ttf", 40)
        img = Image.new("RGB", (1280, 100), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        text_w, text_h = draw.textbbox((0, 0), bidi_text, font=font)[2:]
        draw.text(((1280 - text_w) / 2, (100 - text_h) / 2), bidi_text, fill=(0, 0, 0), font=font)
        text_img_path = "text.png"
        img.save(text_img_path)

        # יצירת קליפ של הכתובית
        clip = VideoFileClip(input_path)
        txt_clip = ImageClip(text_img_path).set_duration(clip.duration).set_position(("center", "bottom"))
        final = CompositeVideoClip([clip, txt_clip])
        output_path = "output.mp4"
        final.write_videofile(output_path, codec='libx264', audio_codec='aac')

        with open(output_path, 'rb') as video:
            bot.send_video(message.chat.id, video, caption="🎬 הנה הסרטון המתורגם שלך!")

        os.remove(input_path)
        os.remove(output_path)
        os.remove(text_img_path)

    except Exception as e:
        bot.reply_to(message, f"שגיאה בעיבוד הסרטון: {e}")

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
