import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from deep_translator import GoogleTranslator
from moviepy.editor import VideoFileClip, CompositeVideoClip, TextClip
import tempfile
from flask import Flask
from threading import Thread
import requests
import gc
from arabic_reshaper import reshape
from bidi.algorithm import get_display
import time

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

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
    """תמלול אודיו באמצעות Groq API עם retry ו-error handling"""
    GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
    
    if not GROQ_API_KEY:
        raise Exception("GROQ_API_KEY לא מוגדר!")
    
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}"
    }
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Groq transcription attempt {attempt + 1}/{max_retries}")
            
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
                logger.info("✅ Groq transcription successful")
                return response.json()
            
            elif response.status_code == 429:  # Rate limit
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 5
                    logger.warning(f"Rate limited, waiting {wait_time}s before retry {attempt + 2}")
                    time.sleep(wait_time)
                    continue
                    
            elif response.status_code >= 500:  # Server error
                if attempt < max_retries - 1:
                    wait_time = 3
                    logger.warning(f"Server error {response.status_code}, retrying in {wait_time}s")
                    time.sleep(wait_time)
                    continue
            
            raise Exception(f"Groq API Error {response.status_code}: {response.text[:200]}")
            
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                logger.warning(f"Timeout, retry {attempt + 2}/{max_retries}")
                time.sleep(2)
                continue
            raise Exception("Groq API timeout after all retries")
            
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                logger.warning(f"Request error: {e}, retry {attempt + 2}/{max_retries}")
                time.sleep(2)
                continue
            raise Exception(f"Groq API request failed: {str(e)[:200]}")
            
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"Error: {e}, retry {attempt + 2}/{max_retries}")
                time.sleep(2)
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
        # fallback - החזרת הטקסט המקורי
        return text

def create_subtitle_clip(text, start, duration, video_size):
    """יצירת כתובית עם TextClip - ללא תלות ב-ImageMagick"""
    
    # תיקון הטקסט העברי
    hebrew_text = fix_hebrew_text(text)
    
    try:
        # יצירת כתובית עם TextClip - שימוש ב-label במקום caption
        txt_clip = TextClip(
            hebrew_text,
            fontsize=46,
            color='white',
            font='DejaVu-Sans-Bold',
            stroke_color='black',
            stroke_width=2,
            method='label',  # label עובד יותר טוב מ-caption
            transparent=True
        )
        
        # הוספת רקע שחור חצי שקוף לקריאות
        from moviepy.video.VideoClip import ColorClip
        
        # חישוב גודל רקע בטוח
        bg_width = min(txt_clip.w + 40, video_size[0] - 40)
        bg_height = txt_clip.h + 20
        
        bg_clip = ColorClip(
            size=(bg_width, bg_height),
            color=(0, 0, 0)
        ).set_opacity(0.75)
        
        # הגדרת זמנים
        bg_clip = bg_clip.set_start(start).set_duration(duration)
        txt_clip = txt_clip.set_start(start).set_duration(duration)
        
        # מיקום בתחתית המסך
        y_position = video_size[1] - bg_height - 40
        bg_clip = bg_clip.set_position(('center', y_position))
        txt_clip = txt_clip.set_position(('center', y_position + 10))
        
        return [bg_clip, txt_clip]
        
    except Exception as e:
        logger.error(f"Error creating subtitle with background: {e}")
        
        # Fallback - כתובית פשוטה ללא רקע
        try:
            txt_clip = TextClip(
                hebrew_text,
                fontsize=46,
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
            logger.error(f"Error in fallback subtitle: {e2}")
            return []

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    video_path = None
    audio_path = None
    output_path = None
    video = None
    final_video = None
    temp_audio_file = None
    
    try:
        # בדיקת גודל
        if update.message.video.file_size > 20 * 1024 * 1024:
            await update.message.reply_text("❌ הסרטון גדול מדי! מקסימום 20MB")
            return
        
        status_msg = await update.message.reply_text("⏳ מעבד את הסרטון...")
        
        # הורדת הסרטון
        logger.info("Downloading video...")
        video_file = await update.message.video.get_file()
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as temp_video:
            await video_file.download_to_drive(temp_video.name)
            video_path = temp_video.name
        
        logger.info(f"✅ Video downloaded: {video_path}")
        
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
        
        # חילוץ אודיו
        audio_path = video_path.replace('.mp4', '.mp3')
        video.audio.write_audiofile(audio_path, verbose=False, logger=None)
        
        video_size = video.size
        logger.info(f"📐 Video size: {video_size}, duration: {video.duration:.2f}s")
        
        # שחרור הסרטון זמנית לחיסכון בזיכרון
        video.close()
        video = None
        gc.collect()
        
        # תמלול עם Groq
        await status_msg.edit_text("🗣️ מתמלל דיבור עם Groq AI...")
        try:
            result = transcribe_with_groq(audio_path)
            segments = result.get('segments', [])
        except Exception as e:
            logger.error(f"Groq transcription error: {e}")
            await update.message.reply_text(f"❌ שגיאה בתמלול: {str(e)[:150]}")
            return
        
        logger.info(f"📝 Found {len(segments)} speech segments")
        
        if not segments:
            await update.message.reply_text("❌ לא נמצא דיבור באודיו")
            return
        
        # תרגום לעברית
        await status_msg.edit_text("🌍 מתרגם לעברית...")
        translator = GoogleTranslator(source='en', target='iw')  # 'iw' = עברית!
        
        subtitles = []
        failed_translations = 0
        
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
                    logger.info(f"✅ [{i+1}/{len(segments)}] {text[:25]}... → {translated[:25]}...")
                except Exception as e:
                    failed_translations += 1
                    logger.error(f"❌ Translation failed for segment {i+1}: {e}")
                    # המשך עם הטקסט באנגלית במקרה של כשל
                    subtitles.append({
                        'start': seg['start'],
                        'end': seg['end'],
                        'text': text
                    })
                    continue
        
        if not subtitles:
            await update.message.reply_text("❌ לא הצלחתי לתרגם את הטקסט")
            return
        
        if failed_translations > 0:
            logger.warning(f"⚠️ {failed_translations} translations failed")
        
        logger.info(f"✅ Created {len(subtitles)} subtitles")
        
        # הוספת כתוביות
        await status_msg.edit_text(f"🎨 מוסיף {len(subtitles)} כתוביות...")
        
        # פתיחת הסרטון שוב
        video = VideoFileClip(video_path)
        
        # יצירת כתוביות
        all_clips = [video]
        failed_subs = 0
        
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
                    logger.info(f"✅ Subtitle {i+1}/{len(subtitles)} created")
                else:
                    failed_subs += 1
                    
                # עדכון כל 5 כתוביות
                if (i + 1) % 5 == 0:
                    try:
                        await status_msg.edit_text(f"🎨 מוסיף כתוביות... ({i+1}/{len(subtitles)})")
                    except:
                        pass
                        
            except Exception as e:
                failed_subs += 1
                logger.error(f"❌ Failed to create subtitle {i+1}: {e}")
                continue
        
        if len(all_clips) <= 1:
            await update.message.reply_text("❌ נכשל ביצירת כתוביות")
            video.close()
            return
        
        if failed_subs > 0:
            logger.warning(f"⚠️ {failed_subs} subtitles failed to create")
        
        logger.info(f"✅ Created {len(all_clips)-1} subtitle elements")
        
        # שילוב הסרטון עם הכתוביות
        await status_msg.edit_text("🎬 מרכיב את הסרטון הסופי...")
        
        final_video = CompositeVideoClip(all_clips)
        output_path = video_path.replace('.mp4', '_sub.mp4')
        temp_audio_file = video_path.replace('.mp4', '_temp_audio.m4a')
        
        # כתיבת הסרטון
        logger.info("Writing final video...")
        final_video.write_videofile(
            output_path,
            codec='libx264',
            audio_codec='aac',
            preset='ultrafast',
            threads=2,
            verbose=False,
            logger=None,
            temp_audiofile=temp_audio_file
        )
        
        logger.info("✅ Video rendering complete!")
        
        # שליחת הסרטון
        await status_msg.edit_text("📤 שולח את הסרטון...")
        
        file_size = os.path.getsize(output_path)
        logger.info(f"📦 Output file size: {file_size / 1024 / 1024:.2f}MB")
        
        caption = "✅ סרטון עם כתוביות בעברית!\n⚡ Powered by Groq"
        if failed_translations > 0 or failed_subs > 0:
            caption += f"\n⚠️ {failed_translations + failed_subs} כתוביות נכשלו"
        
        with open(output_path, 'rb') as f:
            await update.message.reply_video(
                video=f,
                caption=caption,
                read_timeout=120,
                write_timeout=120,
                connect_timeout=60
            )
        
        await status_msg.delete()
        logger.info("✅ SUCCESS! Video sent to user")
        
    except Exception as e:
        logger.error(f"❌ CRITICAL ERROR: {e}", exc_info=True)
        try:
            error_msg = str(e)[:200]
            await update.message.reply_text(f"❌ שגיאה: {error_msg}\n\nנסה שוב עם סרטון אחר")
        except:
            pass
    
    finally:
        # ניקוי יסודי
        logger.info("🧹 Cleaning up temporary files...")
        
        # סגירת כל הקליפים
        try:
            if final_video:
                final_video.close()
                del final_video
        except Exception as e:
            logger.error(f"Error closing final_video: {e}")
        
        try:
            if video:
                video.close()
                del video
        except Exception as e:
            logger.error(f"Error closing video: {e}")
        
        # מחיקת כל הקבצים הזמניים
        temp_files = [video_path, audio_path, output_path, temp_audio_file]
        
        for file_path in temp_files:
            try:
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"🗑️ Deleted: {file_path}")
            except Exception as e:
                logger.error(f"Failed to delete {file_path}: {e}")
        
        # ניקוי זיכרון
        gc.collect()
        logger.info("✅ Cleanup complete")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Telegram error: {context.error}", exc_info=context.error)

def run_bot():
    TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
    
    if not TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN לא מוגדר!")
        return
    
    GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
    if not GROQ_API_KEY:
        logger.error("❌ GROQ_API_KEY לא מוגדר!")
        return
    
    logger.info("🔑 Environment variables loaded successfully")
    
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.VIDEO, handle_video))
    application.add_error_handler(error_handler)
    
    logger.info("🤖 Bot starting with Groq AI...")
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
    logger.info(f"🌐 Flask starting on port {port}")
    app.run(host='0.0.0.0', port=port, threaded=True)

if __name__ == '__main__':
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    run_bot()
