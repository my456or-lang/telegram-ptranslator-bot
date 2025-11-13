from flask import Flask, request
import telebot
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
from deep_translator import GoogleTranslator
from bidi.algorithm import get_display
import arabic_reshaper
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
        file_info = bot.get_file(message.video.file_id)
        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"
        input_path = "input.mp4"
        os.system(f"curl -L '{file_url}' -o {input_path}")

        # טקסט לדוגמה (בהמשך נחלץ מהוידאו)
        text = "Hello world"

        # תרגום לעברית
        translated = GoogleTranslator(source='auto', target='iw').translate(text)
        reshaped = arabic_reshaper.reshape(translated)
        bidi_text = get_display(reshaped)

        # הוספת כתוביות
        clip = VideoFileClip(input_path)
        txt_clip = TextClip(bidi_text, fontsize=40, color='black', bg_color='white', font='Arial')
        txt_clip = txt_clip.set_duration(clip.duration).set_position(('center', 'bottom'))
        final = CompositeVideoClip([clip, txt_clip])
        output_path = "output.mp4"
        final.write_videofile(output_path, codec='libx264', audio_codec='aac')

        # שליחת הסרטון המתורגם
        with open(output_path, 'rb') as video:
            bot.send_video(message.chat.id, video, caption="🎬 הנה הסרטון המתורגם שלך!")

        os.remove(input_path)
        os.remove(output_path)

    except Exception as e:
        bot.reply_to(message, f"שגיאה בעיבוד הסרטון: {e}")

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
