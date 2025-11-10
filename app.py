import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from deep_translator import GoogleTranslator
from moviepy.editor import VideoFileClip, CompositeVideoClip, TextClip
import tempfile
from flask import Flask
from threading import Thread, Semaphore
import requests
import gc
from arabic_reshaper import reshape
from bidi.algorithm import get_display
import uuid
import time

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# הגבלה ל-2 עיבודים בו זמנית (למנוע עומס!)
processing_semaphore = Semaphore(2)

app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Bot is running with Groq!"

@app.route('/health')
def health():
    return "OK", 200

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 שלום! אני בוט תרגום כתוביות (Powered by Groq ⚡)\n\n"
        "שלח לי סרטון עם אודיו באנגלית,\n"
        "ואני אחזיר לך את הסרטון עם כתוביות בעברית! 🇮🇱\n\n"
        "📹 פשוט שלח סרטון ואני אתחיל...\n\n"
        "⚠️ מגבלות:\n"
        "• סרטון עד 5 דקות\n"
        "• גודל עד 20MB\n\n"
        "⚡ כתוביות עם רקע קריא!"
    )

def transcribe_with_groq(audio_path, max_retries=3):
    """תמלול אודיו באמצעות Groq API עם retry"""
    GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
    
    if not GROQ_API_KEY:
        raise Exception("GROQ_API_KEY לא מוגדר!")
    
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}"
    }
    
    for attempt in range(max_retries):
        try:
            with open(audio_path, 'rb') as audio_file:
                files = {
                    'file': audio_file,
                    'model': (None, 'whisper-large-v3'),
                    'language': (None, 'en'),
                    'response_format': (None, 'verbose_json'),
                    'timestamp_granularities[]': (None, 'segment')
                }
                
                response = requests.post(url, headers=headers, files=files, timeout=300)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:  # Rate limit
                if attempt < max_retries - 1:
                    logger.warning(f"Rate limited, retry {attempt + 1}/{max_retries}")
                    import time
                    time.sleep(5)
                    continue
            
            raise Exception(f"Groq API Error {response.status_code}: {response.text}")
            
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                logger.warning(f"Timeout, retry {attempt + 1}/{max_retries}")
                continue
            raise Exception("Groq API timeout after retries")
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"Error, retry {attempt + 1}/{max_retries}: {e}")
                continue
            raise
    
    raise Exception("Failed after all retries")

def fix_hebrew_text(text):
    """
    תיקון טקסט עברי למימין לשמאל - הדרך הנכונה!
    משתמש ב-arabic_reshaper וב-bidi כדי לטפל נכון בעברית
    """
    try:
        # קודם נעצב מחדש את התווים (חשוב לעברית ולערבית)
        reshaped_text = reshape(text)
        # אחר כך נחיל את האלגוריתם הדו-כיווני
        bidi_text = get_display(reshaped_text)
        return bidi_text
    except Exception as e:
        logger.error(f"Error fixing Hebrew text: {e}")
        # fallback - לפחות נחזיר את הטקסט המקורי
        return text

def create_subtitle_clip(text, start, duration, video_size):
    """יצירת כתובית עם TextClip - גרסה יציבה ללא ImageMagick מורכב"""
    
    # תיקון הטקסט העברי
    hebrew_text = fix_hebrew_text(text)
    
    try:
        # יצירת כתובית עם TextClip - שימוש ב-label (יותר יציב)
        txt_clip = TextClip(
            hebrew_text,
            fontsize=46,
            color='white',
            font='DejaVu-Sans-Bold',
            stroke_color='black',
            stroke_width=2,
            method='label',  # label במקום caption - פחות תלוי ב-ImageMagick
            align='center'
        )
        
        # הוספת רקע שחור חצי שקוף
        from moviepy.video.VideoClip import ColorClip
        
        # חישוב גודל בטוח
        txt_width = min(txt_clip.w + 40, video_size[0] - 40)
        txt_height = txt_clip.h + 20
        
        bg_clip = ColorClip(
            size=(txt_width, txt_height),
            color=(0, 0, 0)
        ).set_opacity(0.75)
        
        # הגדרת זמנים
        bg_clip = bg_clip.set_start(start).set_duration(duration)
        txt_clip = txt_clip.set_start(start).set_duration(duration)
        
        # מיקום בתחתית המסך
        y_position = video_size[1] - txt_height - 40
        bg_clip = bg_clip.set_position(('center', y_position))
        txt_clip = txt_clip.set_position(('center', y_position + 10))
        
        return [bg_clip, txt_clip]
        
    except Exception as e:
        logger.error(f"Error creating TextClip: {e}")
        # ניסיון fallback פשוט ללא רקע
        try:
            txt_clip = TextClip(
                hebrew_text,
                fontsize=44,
                color='white',
                font='DejaVu-Sans-Bold',
                stroke_color='black',
                stroke_width=3,
                method='label'
            )
            txt_clip = txt_clip.set_start(start).set_duration(duration)
            txt_clip = txt_clip.set_position(('center', video_size[1] - 70))
            return [txt_clip]
        except Exception as e2:
            logger.error(f"Fallback also failed: {e2}")
            return []

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # בדיקה אם יש מקום פנוי לעיבוד
    if not processing_semaphore.acquire(blocking=False):
        await update.message.reply_text(
            "⏳ הבוט עסוק כרגע בעיבוד סרטונים אחרים.\n"
            "נסה שוב בעוד 30 שניות... 🙏"
        )
        return
    
    # יצירת ID ייחודי לכל סשן - פותר קונפליקט בין משתמשים!
    session_id = str(uuid.uuid4())[:8]
    user_id = update.message.from_user.id
    
    video_path = None
    audio_path = None
    output_path = None
    video = None
    final_video = None
    temp_audio_path = None
    
    try:
        # בדיקת גודל
        if update.message.video.file_size > 20 * 1024 * 1024:
            await update.message.reply_text("❌ הסרטון גדול מדי! מקסימום 20MB")
            return
        
        status_msg = await update.message.reply_text("⏳ מעבד את הסרטון...")
        
        # הורדת הסרטון עם שם ייחודי
        video_file = await update.message.video.get_file()
        
        # יצירת קובץ עם שם ייחודי למשתמש
        with tempfile.NamedTemporaryFile(delete=False, suffix=f'_{session_id}_{user_id}.mp4', dir='/tmp') as temp_video:
            await video_file.download_to_drive(temp_video.name)
            video_path = temp_video.name
        
        logger.info(f"✅ Video downloaded: {video_path} [User: {user_id}, Session: {session_id}]")
        
        # פתיחת הסרטון
        await status_msg.edit_text("🎤 מחלץ אודיו...")
        video = VideoFileClip(video_path)
        
        # בדיקת אורך
        if video.duration > 300:  # 5 דקות
            await update.message.reply_text("❌ הסרטון ארוך מדי! מקסימום 5 דקות")
            video.close()
            return
        
        # בדיקת אודיו
        if video.audio is None:
            await update.message.reply_text("❌ הסרטון לא מכיל אודיו!")
            video.close()
            return
        
        # חילוץ אודיו עם שם ייחודי
        audio_path = f'/tmp/audio_{session_id}_{user_id}.mp3'
        video.audio.write_audiofile(audio_path, verbose=False, logger=None)
        
        video_size = video.size
        logger.info(f"📐 Video size: {video_size}")
        
        # שחרור הסרטון זמנית לחיסכון בזיכרון
        video.close()
        video = None
        gc.collect()
        
        # תמלול עם Groq
        await status_msg.edit_text("🗣️ מתמלל דיבור...")
        try:
            result = transcribe_with_groq(audio_path)
            segments = result.get('segments', [])
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            await update.message.reply_text(f"❌ שגיאה בתמלול: {str(e)[:100]}")
            return
        
        logger.info(f"📝 Found {len(segments)} segments")
        
        if not segments:
            await update.message.reply_text("❌ לא נמצא דיבור באודיו")
            return
        
        # תרגום
        await status_msg.edit_text("🌍 מתרגם לעברית...")
        translator = GoogleTranslator(source='en', target='iw')  # 'iw' = עברית ב-Google!
        
        subtitles = []
        for i, seg in enumerate(segments):
            text = seg.get('text', '').strip()
            if text and len(text) > 2:
                try:
                    translated = translator.translate(text)
                    subtitles.append({
                        'start': seg['start'],
                        'end': seg['end'],
                        'text': translated
                    })
                    logger.info(f"✅ {i+1}/{len(segments)}: {text[:30]}... → {translated[:30]}...")
                except Exception as e:
                    logger.error(f"❌ Translation error for segment {i}: {e}")
                    continue
        
        if not subtitles:
            await update.message.reply_text("❌ לא נמצא טקסט לתרגום")
            return
        
        logger.info(f"✅ Created {len(subtitles)} Hebrew subtitles")
        
        # הוספת כתוביות
        await status_msg.edit_text(f"🎨 מוסיף {len(subtitles)} כתוביות...")
        
        # פתיחת הסרטון שוב
        video = VideoFileClip(video_path)
        
        # יצירת כתוביות
        all_clips = [video]
        
        for i, sub in enumerate(subtitles):
            try:
                clips = create_subtitle_clip(
                    sub['text'],
                    sub['start'],
                    sub['end'] - sub['start'],
                    video_size
                )
                if clips:
                    all_clips.extend(clips)
                    logger.info(f"✅ Subtitle {i+1}/{len(subtitles)}")
                    
                    # עדכון כל 5 כתוביות
                    if (i + 1) % 5 == 0:
                        try:
                            await status_msg.edit_text(f"🎨 מוסיף כתוביות... ({i+1}/{len(subtitles)})")
                        except:
                            pass
            except Exception as e:
                logger.error(f"❌ Failed subtitle {i}: {e}")
                continue
        
        if len(all_clips) <= 1:
            await update.message.reply_text("❌ נכשל ביצירת כתוביות")
            video.close()
            return
        
        logger.info(f"✅ Created {len(all_clips)-1} subtitle clips")
        
        # שילוב הסרטון עם הכתוביות
        await status_msg.edit_text("🎬 מרכיב את הסרטון הסופי...")
        
        final_video = CompositeVideoClip(all_clips)
        output_path = f'/tmp/output_{session_id}_{user_id}.mp4'
        temp_audio_path = f'/tmp/temp_audio_{session_id}_{user_id}.m4a'
        
        # כתיבת הסרטון
        final_video.write_videofile(
            output_path,
            codec='libx264',
            audio_codec='aac',
            preset='ultrafast',
            threads=2,
            verbose=False,
            logger=None,
            temp_audiofile=temp_audio_path
        )
        
        logger.info("✅ Video complete!")
        
        # שליחת הסרטון
        await status_msg.edit_text("📤 שולח...")
        
        file_size = os.path.getsize(output_path)
        logger.info(f"📦 Output file size: {file_size / 1024 / 1024:.2f}MB")
        
        with open(output_path, 'rb') as f:
            await update.message.reply_video(
                video=f,
                caption="✅ סרטון עם כתוביות בעברית!\n⚡ Powered by Groq",
                read_timeout=120,
                write_timeout=120,
                connect_timeout=60
            )
        
        await status_msg.delete()
        logger.info("✅ SUCCESS!")
        
    except Exception as e:
        logger.error(f"❌ ERROR: {e}", exc_info=True)
        try:
            await update.message.reply_text(f"❌ שגיאה: {str(e)[:200]}")
        except:
            pass
    
    finally:
        # ניקוי
        logger.info("🧹 Cleaning up...")
        
        try:
            if final_video:
                final_video.close()
        except:
            pass
        
        try:
            if video:
                video.close()
        except:
            pass
        
        # מחיקת כל הקבצים הזמניים
        temp_files = [video_path, audio_path, output_path, temp_audio_path]
        
        for file_path in temp_files:
            try:
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"🗑️ Deleted: {file_path}")
            except Exception as e:
                logger.error(f"Failed to delete {file_path}: {e}")
        
        gc.collect()
        logger.info("✅ Cleanup complete")
    
    finally:
        # שחרור ה-semaphore כדי לאפשר למשתמש הבא
        processing_semaphore.release()
        logger.info(f"🔓 Released processing slot [Session: {session_id}]")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception: {context.error}", exc_info=context.error)

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
    
    logger.info("🤖 Bot starting with Groq...")
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        pool_timeout=60,
        read_timeout=60,
        write_timeout=60,
        connect_timeout=60
    )

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, threaded=True)

if __name__ == '__main__':
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    run_bot()
