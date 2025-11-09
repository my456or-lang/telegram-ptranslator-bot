import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from deep_translator import GoogleTranslator
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
import tempfile
from flask import Flask
from threading import Thread
import requests
import gc

# --- לוגים ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Flask לצורך שמירה על חיות השרת ---
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Bot is running!"

@app.route('/health')
def health():
    return "OK", 200

# --- הפקודה /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 שלום! שלח לי סרטון (עד 10 דקות / עד 50MB) ואני אחזיר אותו עם כתוביות בעברית."
    )

# --- תמלול עם Groq (מעלים קובץ אודיו ומקבלים JSON) ---
def transcribe_with_groq(audio_path):
    GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
    if not GROQ_API_KEY:
        raise Exception("GROQ_API_KEY לא מוגדר!")

    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}

    with open(audio_path, 'rb') as audio_file:
        files = {
            'file': audio_file,
            'model': (None, 'whisper-large-v3'),
            'language': (None, 'en'),
            'response_format': (None, 'verbose_json'),
            'timestamp_granularities[]': (None, 'segment')
        }
        response = requests.post(url, headers=headers, files=files, timeout=300)

    if response.status_code != 200:
        raise Exception(f"Groq API Error: {response.text}")

    return response.json()

# --- טיפול בסרטון מהמשתמש ---
async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    video_path = None
    audio_path = None
    output_path = None
    video = None

    try:
        if not update.message.video:
            await update.message.reply_text("אנא שלח/י קובץ וידאו (לא קובץ מדיה אחר).")
            return

        if update.message.video.file_size > 50 * 1024 * 1024:
            await update.message.reply_text("❌ הסרטון גדול מדי! מקסימום 50MB")
            return

        status_msg = await update.message.reply_text("⏳ מוריד ומעבד את הסרטון...")

        # הורדת הסרטון לטמפ
        video_file = await update.message.video.get_file()
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as temp_video:
            await video_file.download_to_drive(temp_video.name)
            video_path = temp_video.name

        await status_msg.edit_text("🎤 מחלץ אודיו...")

        video = VideoFileClip(video_path)
        if video.duration > 600:
            await update.message.reply_text("❌ הסרטון ארוך מדי! מקסימום 10 דקות")
            video.close()
            os.remove(video_path)
            return

        audio_path = video_path.replace('.mp4', '.mp3')
        video.audio.write_audiofile(audio_path, verbose=False, logger=None)

        video.close()
        video = None
        gc.collect()

        await status_msg.edit_text("🗣️ מתמלל את האודיו (Groq)...")

        result = transcribe_with_groq(audio_path)
        segments = result.get('segments', [])

        if not segments:
            await update.message.reply_text("❌ לא נמצא דיבור באודיו")
            return

        gc.collect()

        await status_msg.edit_text("🌍 מתרגם לעברית...")

        translator = GoogleTranslator(source='en', target='iw')
        subtitles = []
        for seg in segments:
            text = seg.get('text', '').strip()
            if text and len(text) > 1:
                try:
                    translated = translator.translate(text)
                    subtitles.append({
                        'start': seg['start'],
                        'end': seg['end'],
                        'text': translated
                    })
                except Exception:
                    continue

        if not subtitles:
            await update.message.reply_text("❌ לא נמצא טקסט לתרגום")
            return

        await status_msg.edit_text("🎨 מייצר כתוביות על הסרטון...")

        # נתיב לפונט בעברית — ודא שהקובץ קיים בתיקיית fonts/
        font_path = "fonts/NotoSansHebrew-Regular.ttf"

        video = VideoFileClip(video_path)
        txt_clips = []

        for sub in subtitles:
            # לפעמים צריך להפוך מחרוזת RTL — ננסה הפיכה כדי להבטיח קריאות
            text_to_write = sub['text'][::-1]

            txt_clip = (TextClip(
                text_to_write,
                fontsize=28,
                color='white',
                bg_color='black',
                font=font_path,
                method='caption',
                size=(int(video.w * 0.85), None)
            )
            .set_position(('center', int(video.h * 0.82)))
            .set_start(sub['start'])
            .set_duration(sub['end'] - sub['start']))

            txt_clips.append(txt_clip)

        final_video = CompositeVideoClip([video] + txt_clips)
        output_path = video_path.replace('.mp4', '_subtitled.mp4')

        final_video.write_videofile(
            output_path,
            codec='libx264',
            audio_codec='aac',
            preset='ultrafast',
            threads=2,
            verbose=False,
            logger=None
        )

        final_video.close()
        video.close()
        gc.collect()

        await status_msg.edit_text("📤 שולח את הסרטון המוכתם...")

        with open(output_path, 'rb') as video_file_to_send:
            await update.message.reply_video(
                video=video_file_to_send,
                caption="✅ הנה הסרטון שלך עם כתוביות בעברית!",
                read_timeout=120,
                write_timeout=120
            )

        await status_msg.delete()

    except Exception as e:
        logger.exception("שגיאה במהלך עיבוד הווידאו")
        try:
            await update.message.reply_text(f"❌ שגיאה: {str(e)}")
        except:
            pass

    finally:
        for file_path in [video_path, audio_path, output_path]:
            try:
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
            except Exception:
                pass
        try:
            if video:
                video.close()
        except:
            pass
        gc.collect()

# --- handler לשגיאות כלליות ---
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception: {context.error}")

# --- הפעלת הבוט (Polling) + Flask ---
def run_bot():
    TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
    if not TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN לא מוגדר!")
        return

    GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
    if not GROQ_API_KEY:
        logger.error("❌ GROQ_API_KEY לא מוגדר!")
        return

    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.VIDEO, handle_video))
    application.add_error_handler(error_handler)

    logger.info("🤖 הבוט מתחיל לרוץ...")
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    run_bot()
