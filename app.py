import os
import telebot
import tempfile
import requests
from moviepy.editor import VideoFileClip
from deep_translator import GoogleTranslator
from groq import Groq

BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

bot = telebot.TeleBot(BOT_TOKEN)
client = Groq(api_key=GROQ_API_KEY)

# 🎧 המרת אודיו לטקסט (תמלול)
def transcribe_audio(file_path):
    with open(file_path, "rb") as f:
        transcription = client.audio.transcriptions.create(
            model="whisper-large-v3-turbo",  # ✅ דגם חדש ומהיר
            file=f
        )
    return transcription.text

# 🌍 תרגום טקסט לעברית
def translate_text(text):
    try:
        translated = GoogleTranslator(source="auto", target="he").translate(text)
        return translated
    except Exception as e:
        return f"שגיאה בתרגום: {e}"

# 🧾 יצירת קובץ SRT מהכתוביות
def create_srt(transcript_text, file_path):
    with open(file_path, "w", encoding="utf-8") as f:
        # לצורך ניסוי ניצור כתובית אחת בלבד על כל הטקסט
        f.write("1\n")
        f.write("00:00:00,000 --> 00:00:10,000\n")
        f.write(transcript_text + "\n\n")

# 🎥 טיפול בקובץ וידאו שנשלח
@bot.message_handler(content_types=["video"])
def handle_video(message):
    try:
        bot.reply_to(message, "🎬 מוריד את הסרטון שלך...")
        file_info = bot.get_file(message.video.file_id)
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
        response = requests.get(file_url)
        
        # שמירת קובץ זמני
        video_temp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        video_temp.write(response.content)
        video_temp.close()

        bot.reply_to(message, "🎧 ממיר את הדיבור לטקסט...")
        text = transcribe_audio(video_temp.name)

        if not text:
            bot.reply_to(message, "❌ לא הצלחתי לזהות דיבור.")
            return

        bot.reply_to(message, "🔠 מתרגם לעברית...")
        translated = translate_text(text)

        bot.reply_to(message, "📄 יוצר קובץ כתוביות (SRT)...")
        srt_path = tempfile.NamedTemporaryFile(delete=False, suffix=".srt").name
        create_srt(translated, srt_path)

        bot.reply_to(message, "✅ הנה קובץ הכתוביות שלך (בעברית):")
        with open(srt_path, "rb") as srt_file:
            bot.send_document(message.chat.id, srt_file)

    except Exception as e:
        bot.reply_to(message, f"❌ קרתה שגיאה בעת יצירת הכתוביות.\n\n{e}")

# 🟢 הפעלת הבוט
if __name__ == "__main__":
    print("🤖 הבוט פעיל ומוכן לעבודה...")
    bot.polling(none_stop=True)
