import os
import telebot
import tempfile
import requests
from moviepy.editor import VideoFileClip, CompositeVideoClip, ImageClip
from PIL import Image, ImageDraw, ImageFont
from deep_translator import GoogleTranslator
from groq import Groq

# משתני סביבה
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

bot = telebot.TeleBot(BOT_TOKEN)
client = Groq(api_key=GROQ_API_KEY)

# יצירת טקסט-קליפ בעזרת PIL (ללא ImageMagick)
def create_text_clip(text, fontsize=50, color="white", size=(1280, 720), duration=5):
    # שימוש בגופן כללי שנמצא בכל מערכת לינוקס
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(font_path, fontsize)
    text = text.strip()

    # חישוב מיקום מרכזי
    w, h = draw.textbbox((0, 0), text, font=font)[2:]
    position = ((size[0] - w) / 2, size[1] - h - 50)

    # כתיבת הטקסט
    draw.text(position, text, fill=color, font=font)

    # המרה ל-ImageClip
    return ImageClip(img).set_duration(duration)

# תרגום בעזרת Google Translator
def translate_text(text):
    try:
        return GoogleTranslator(source="auto", target="he").translate(text)
    except Exception:
        return text

# המרת אודיו לטקסט באמצעות Groq (Whisper)
def transcribe_audio(file_path):
    with open(file_path, "rb") as f:
        transcription = client.audio.transcriptions.create(
            model="whisper-large-v3",
            file=f
        )
    return transcription.text

# טיפול בהודעת וידאו
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

        bot.reply_to(message, "🔠 מתרגם לעברית...")
        translated = translate_text(text)

        bot.reply_to(message, "🎞️ מוסיף כתוביות לסרטון...")

        # טעינת הסרטון
        clip = VideoFileClip(video_temp.name)

        # יצירת קליפ כתוביות
        text_clip = create_text_clip(translated, fontsize=45, duration=clip.duration, size=clip.size)

        # שילוב הסרטון עם הטקסט
        final = CompositeVideoClip([clip, text_clip])
        output_path = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4").name
        final.write_videofile(output_path, codec="libx264", audio_codec="aac")

        bot.reply_to(message, "✅ הנה הסרטון שלך עם כתוביות בעברית:")
        with open(output_path, "rb") as video_out:
            bot.send_video(message.chat.id, video_out)

    except Exception as e:
        bot.reply_to(message, f"❌ שגיאה בעיבוד הסרטון:\n\n{e}")

# התחלת האזנה
if __name__ == "__main__":
    print("🤖 הבוט פעיל ומוכן לעבודה...")
    bot.polling(none_stop=True)
