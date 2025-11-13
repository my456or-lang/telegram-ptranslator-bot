import os
import telebot
from groq import Groq
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
from deep_translator import GoogleTranslator
import tempfile

# --- משתני סביבה ---
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

# --- אתחול לקוחות ---
bot = telebot.TeleBot(BOT_TOKEN)
client = Groq(api_key=GROQ_API_KEY)


# --- פונקציה לתמלול אודיו ---
def transcribe_audio(audio_path):
    with open(audio_path, "rb") as f:
        result = client.audio.transcriptions.create(
            model="whisper-large-v3",
            file=f
        )

    text = getattr(result, "text", None)
    if not text:
        raise ValueError("לא התקבלה תוצאה תקינה מהתמלול.")
    return text.strip()


# --- פונקציה להוספת כתוביות ---
def add_subtitles(video_path, text):
    clip = VideoFileClip(video_path)
    translated_text = GoogleTranslator(source="en", target="he").translate(text)

    txt_clip = TextClip(translated_text, fontsize=40, color="white", font="Arial-Bold")
    txt_clip = txt_clip.set_position(("center", "bottom")).set_duration(clip.duration)

    final = CompositeVideoClip([clip, txt_clip])
    temp_output = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    final.write_videofile(temp_output.name, codec="libx264", audio_codec="aac")

    return temp_output.name


# --- מאזין להודעות ---
@bot.message_handler(commands=["start"])
def send_welcome(message):
    bot.reply_to(
        message,
        "👋 שלח לי סרטון באנגלית ואוסיף לו כתוביות בעברית 🎧📜"
    )


@bot.message_handler(content_types=["video", "document"])
def handle_video(message):
    try:
        bot.reply_to(message, "🎬 מוריד את הסרטון שלך...")
        file_info = bot.get_file(message.video.file_id if message.content_type == "video" else message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_file:
            temp_file.write(downloaded_file)
            video_path = temp_file.name

        bot.reply_to(message, "🎧 ממיר את הדיבור לטקסט...")
        text = transcribe_audio(video_path)

        bot.reply_to(message, "🌍 מתרגם ומוסיף כתוביות...")
        output_path = add_subtitles(video_path, text)

        with open(output_path, "rb") as video:
            bot.send_video(message.chat.id, video)

    except Exception as e:
        bot.reply_to(message, f"❌ שגיאה בעיבוד הסרטון:\n\n{e}")


bot.polling()
