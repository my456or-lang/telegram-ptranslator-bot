import os
import telebot
import tempfile
import requests
from moviepy.editor import VideoFileClip
from deep_translator import GoogleTranslator
from groq import Groq
from flask import Flask
import threading

BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

bot = telebot.TeleBot(BOT_TOKEN)
client = Groq(api_key=GROQ_API_KEY)

# 🎧 תמלול אודיו
def transcribe_audio(file_path):
    with open(file_path, "rb") as f:
        transcription = client.audio.transcriptions.create(
            model="whisper-large-v3-turbo",
            file=f
        )
    return transcription.text

# 🌍 תרגום לעברית
def translate_text(text):
    try:
        return GoogleTranslator(source="auto", target="he").translate(text)
    except Exception as e:
        return f"שגיאה בתרגום: {e}"

# 🧾 יצירת SRT
def create_srt(transcript_text, file_path):
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("1\n")
        f.write("00:00:00,000 --> 00:00:10,000\n")
        f.write(transcript_text + "\n\n")

# 🎥 טיפול בוידאו
@bot.message_handler(content_types=["video"])
def handle_video(message):
    try:
        bot.reply_to(message, "🎬 מוריד את הסרטון...")
        file_info = bot.get_file(message.video.file_id)
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
        response = requests.get(file_url)

        tmp_video = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        tmp_video.write(response.content)
        tmp_video.close()

        bot.reply_to(message, "🎧 ממיר לדיבור → טקסט...")
        text = transcribe_audio(tmp_video.name)

        bot.reply_to(message, "🔠 מתרגם לעברית...")
        translated = translate_text(text)

        srt_path = tempfile.NamedTemporaryFile(delete=False, suffix=".srt").name
        create_srt(translated, srt_path)

        bot.reply_to(message, "✅ הנה קובץ הכתוביות שלך:")
        with open(srt_path, "rb") as srt_file:
            bot.send_document(message.chat.id, srt_file)

    except Exception as e:
        bot.reply_to(message, f"❌ שגיאה: {e}")

# 🌐 Flask server עבור Render
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

def run_bot():
    bot.infinity_polling()

if __name__ == "__main__":
    threading.Thread(target=run_bot).start()
    run_web()
