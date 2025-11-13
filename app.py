import os
import telebot
import tempfile
import requests
import langdetect
from deep_translator import GoogleTranslator
from groq import Groq

# 🔧 משתני סביבה
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

bot = telebot.TeleBot(BOT_TOKEN)
client = Groq(api_key=GROQ_API_KEY)

# 🎧 המרת אודיו לטקסט (Groq Whisper)
def transcribe_audio(file_path):
    with open(file_path, "rb") as f:
        transcription = client.audio.transcriptions.create(
            model="whisper-large-v3",
            file=f
        )
    return transcription.text

# 🌍 תרגום טקסט (כולל זיהוי שפה אוטומטי)
def translate_text_auto(text):
    try:
        detected_lang = langdetect.detect(text)
        if detected_lang == "he":
            return text  # כבר בעברית
        return GoogleTranslator(source="auto", target="he").translate(text)
    except Exception as e:
        print(f"Translation error: {e}")
        return text

# 🧾 יצירת קובץ כתוביות SRT פשוט
def create_srt_from_text(text):
    lines = text.split(". ")
    srt_lines = []
    start_time = 0
    index = 1
    for line in lines:
        end_time = start_time + 3
        srt_lines.append(f"{index}\n00:00:{start_time:02d},000 --> 00:00:{end_time:02d},000\n{line}\n")
        start_time += 3
        index += 1
    return "\n".join(srt_lines)

# 🎬 טיפול בקובץ וידאו
@bot.message_handler(content_types=["video"])
def handle_video(message):
    try:
        bot.reply_to(message, "🎬 מוריד את הסרטון שלך...")
        file_info = bot.get_file(message.video.file_id)
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
        response = requests.get(file_url)
        video_temp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        video_temp.write(response.content)
        video_temp.close()

        bot.reply_to(message, "🎧 ממיר את הדיבור לטקסט...")
        text = transcribe_audio(video_temp.name)

        if not text:
            bot.reply_to(message, "❌ לא הצלחתי לזהות דיבור.")
            return

        bot.reply_to(message, "🌍 מתרגם לעברית...")
        translated = translate_text_auto(text)

        srt_content = create_srt_from_text(translated)

        # שמירת קובץ SRT
        srt_path = tempfile.NamedTemporaryFile(delete=False, suffix=".srt").name
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(srt_content)

        bot.reply_to(message, "✅ הנה קובץ הכתוביות שלך (בעברית):")
        with open(srt_path, "rb") as srt_file:
            bot.send_document(message.chat.id, srt_file)

    except Exception as e:
        bot.reply_to(message, f"❌ שגיאה בעיבוד הסרטון:\n\n{e}")

# 🚀 הפעלת הבוט
if __name__ == "__main__":
    print("🤖 הבוט פעיל ומוכן לעבודה...")
    # פורט מדומה לרנדר (כדי שהשירות החינמי לא ייסגר)
    port = int(os.environ.get("PORT", 8080))
    bot.polling(none_stop=True, interval=0)
