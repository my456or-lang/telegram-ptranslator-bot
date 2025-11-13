import os
import telebot
import tempfile
import requests
from deep_translator import GoogleTranslator
from groq import Groq
from langdetect import detect

# === משתני סביבה ===
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

bot = telebot.TeleBot(BOT_TOKEN)
client = Groq(api_key=GROQ_API_KEY)

# === פונקציה לזיהוי שפה ===
def detect_language(text):
    try:
        return detect(text)
    except:
        return "en"

# === פונקציה לתרגום ===
def translate_text(text, target_lang="he"):
    try:
        return GoogleTranslator(source="auto", target=target_lang).translate(text)
    except Exception as e:
        return f"שגיאה בתרגום: {e}"

# === פונקציית תמלול Groq ===
def transcribe_audio(file_path):
    with open(file_path, "rb") as f:
        transcription = client.audio.transcriptions.create(
            model="whisper-large-v3",
            file=f
        )
    return transcription.text

# === טיפול בהודעת וידאו ===
@bot.message_handler(content_types=["video", "voice", "audio"])
def handle_media(message):
    try:
        bot.reply_to(message, "🎧 מוריד את הקובץ ומתחיל בתמלול...")

        # הורדת הקובץ מהטלגרם
        file_info = bot.get_file(message.video.file_id if message.content_type == "video" else message.voice.file_id)
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
        response = requests.get(file_url)

        temp_audio = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        temp_audio.write(response.content)
        temp_audio.close()

        # תמלול
        text = transcribe_audio(temp_audio.name)
        if not text:
            bot.reply_to(message, "❌ לא הצלחתי לזהות דיבור.")
            return

        src_lang = detect_language(text)
        bot.reply_to(message, f"🌍 שפה מזוהה: {src_lang}\n🔠 מתרגם לעברית...")

        translated = translate_text(text, "he")

        # יצירת קובץ .srt בסיסי
        srt_content = "1\n00:00:00,000 --> 00:00:10,000\n" + translated
        srt_file = tempfile.NamedTemporaryFile(delete=False, suffix=".srt")
        srt_file.write(srt_content.encode("utf-8"))
        srt_file.close()

        bot.reply_to(message, "✅ הנה הכתוביות המתורגמות שלך:")
        with open(srt_file.name, "rb") as srt_out:
            bot.send_document(message.chat.id, srt_out, visible_file_name="translated_subtitles.srt")

    except Exception as e:
        bot.reply_to(message, f"❌ שגיאה בעיבוד:\n{e}")

# === הפעלת הבוט ===
if __name__ == "__main__":
    print("🤖 הבוט פעיל ומוכן לעבודה...")
    bot.polling(none_stop=True)
