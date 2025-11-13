import os
import telebot
import tempfile
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
from deep_translator import GoogleTranslator
from groq import Groq
from PIL import ImageFont, Image, ImageDraw
import arabic_reshaper
from bidi.algorithm import get_display
import requests

# --- קריאת משתני סביבה ---
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

# --- אתחול ---
bot = telebot.TeleBot(BOT_TOKEN)
client = Groq(api_key=GROQ_API_KEY)

# --- הודעת התחלה ---
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "👋 שלח לי סרטון באנגלית ואני אוסיף לו כתוביות בעברית 🎧📜")

# --- קבלת סרטון ---
@bot.message_handler(content_types=['video'])
def handle_video(message):
    try:
        bot.reply_to(message, "🎬 מוריד את הסרטון שלך...")

        # הורדת הסרטון
        file_info = bot.get_file(message.video.file_id)
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
        response = requests.get(file_url)
        video_path = tempfile.mktemp(suffix=".mp4")

        with open(video_path, "wb") as f:
            f.write(response.content)

        bot.reply_to(message, "🎧 ממיר את הדיבור לטקסט...")

        # הפקת אודיו מהסרטון
        clip = VideoFileClip(video_path)
        audio_path = tempfile.mktemp(suffix=".wav")
        clip.audio.write_audiofile(audio_path)

        # שליחה ל־Groq לזיהוי דיבור
        with open(audio_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                file=audio_file,
                model="whisper-large-v3"
            )
            english_text = transcript.text

        # תרגום לעברית
        hebrew_text = GoogleTranslator(source='en', target='he').translate(english_text)

        # עיבוד טקסט לעברית (כיוון ימין לשמאל)
        reshaped_text = arabic_reshaper.reshape(hebrew_text)
        bidi_text = get_display(reshaped_text)

        # יצירת כתוביות
        subtitle_path = tempfile.mktemp(suffix=".png")
        font = ImageFont.truetype("arial.ttf", 48)
        img = Image.new("RGBA", (clip.w, 150), (0, 0, 0, 128))
        draw = ImageDraw.Draw(img)
        w, h = draw.textsize(bidi_text, font=font)
        draw.text(((clip.w - w) / 2, 40), bidi_text, font=font, fill="white")
        img.save(subtitle_path)

        subtitle = Image.open(subtitle_path)
        subtitle_clip = (ImageClip(subtitle_path)
                         .set_duration(clip.duration)
                         .set_position(("center", "bottom")))

        final = CompositeVideoClip([clip, subtitle_clip])
        output_path = tempfile.mktemp(suffix=".mp4")
        final.write_videofile(output_path, codec='libx264', audio_codec='aac')

        # שליחת הסרטון חזרה
        with open(output_path, "rb") as vid:
            bot.send_video(message.chat.id, vid, caption="🎬 הנה הסרטון עם כתוביות בעברית!")

    except Exception as e:
        bot.send_message(message.chat.id, f"❌ שגיאה בעיבוד הסרטון: {e}")

# --- הרצת הבוט ---
bot.polling()
