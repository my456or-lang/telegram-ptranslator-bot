import os
import telebot
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
from flask import Flask
import threading
from groq import Groq
from langdetect import detect
import tempfile

# === משתני סביבה ===
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

bot = telebot.TeleBot(BOT_TOKEN)
client = Groq(api_key=GROQ_API_KEY)

# === Flask לצורך פתיחת פורט ===
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Telegram Tokon Bot is running successfully!"

# === פונקציה: זיהוי שפה ותרגום ===
def detect_and_translate(text, target_lang="he"):
    try:
        detected_lang = detect(text)
        if detected_lang == target_lang:
            return text
        response = client.chat.completions.create(
            model="llama-3.2-90b-text-preview",
            messages=[
                {"role": "system", "content": "אתה מתרגם מקצועי."},
                {"role": "user", "content": f"תרגם לעברית: {text}"}
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"שגיאה בתרגום: {e}"

# === יצירת כתוביות על הסרטון ===
def create_subtitled_video(video_path, translated_text):
    try:
        clip = VideoFileClip(video_path)
        txt = TextClip(translated_text,
                       fontsize=40,
                       color='white',
                       font="Arial",
                       method='caption',
                       align='West',
                       size=clip.size)
        txt = txt.set_duration(clip.duration).set_position(("center", "bottom"))
        final = CompositeVideoClip([clip, txt])
        output_path = tempfile.mktemp(suffix=".mp4")
        final.write_videofile(output_path, codec='libx264', audio_codec='aac')
        return output_path
    except Exception as e:
        print("שגיאה ביצירת כתוביות:", e)
        return None

# === האזנה לקובץ וידאו מהמשתמש ===
@bot.message_handler(content_types=['video'])
def handle_video(message):
    try:
        bot.reply_to(message, "🎬 מוריד את הסרטון שלך...")
        file_info = bot.get_file(message.video.file_id)
        downloaded = bot.download_file(file_info.file_path)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp:
            temp.write(downloaded)
            video_path = temp.name

        # יצירת טקסט לדוגמה — אפשר להחליף בזיהוי אמיתי אם תרצה
        text_example = "This is a sample text for translation."
        translated = detect_and_translate(text_example)
        bot.reply_to(message, f"🈶 תרגום לדוגמה:\n{translated}")

        output_path = create_subtitled_video(video_path, translated)
        if output_path:
            with open(output_path, "rb") as vid:
                bot.send_video(message.chat.id, vid, caption="🎞️ סרטון עם כתוביות בעברית מימין לשמאל")
        else:
            bot.reply_to(message, "❌ קרתה שגיאה בעת יצירת הכתוביות.")
    except Exception as e:
        bot.reply_to(message, f"שגיאה: {e}")

# === הרצת הבוט + Flask ===
def start_bot():
    print("🤖 הבוט פועל ומאזין להודעות...")
    bot.polling(non_stop=True, interval=0)

if __name__ == "__main__":
    threading.Thread(target=start_bot).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
