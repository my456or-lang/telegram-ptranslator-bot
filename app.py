import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from deep_translator import GoogleTranslator
from moviepy.editor import VideoFileClip, CompositeVideoClip, VideoClip
import tempfile
from flask import Flask
from threading import Thread
import requests
import gc
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from bidi.algorithm import get_display
import arabic_reshaper

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
        "• סרטון עד 10 דקות\n"
        "• גודל עד 50MB\n\n"
        "⚡ מהיר פי 10 מהגרסה הקודמת!"
    )

def transcribe_with_groq(audio_path):
    """תמלול אודיו באמצעות Groq API"""
    GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
    
    if not GROQ_API_KEY:
        raise Exception("GROQ_API_KEY לא מוגדר!")
    
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}"
    }
    
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

def prepare_hebrew_text(text):
    """
    הכנת טקסט עברי לתצוגה נכונה
    🔥 תיקון קריטי: base_level='R' מאלץ כיוון RTL!
    """
    try:
        reshaped_text = arabic_reshaper.reshape(text)
        # ✅ הוספת base_level='R' - זה מאלץ כיוון מימין לשמאל!
        bidi_text = get_display(reshaped_text, base_dir='R')
        
        logger.info(f"✅ RTL: {text[:20]} → {bidi_text[:20]}")
        return bidi_text
    except Exception as e:
        logger.warning(f"Failed to prepare Hebrew text: {e}")
        # fallback - ניסיון עם base_dir='R' ישירות
        try:
            return get_display(text, base_dir='R')
        except:
            return text[::-1]  # היפוך ידני כפתרון אחרון

def get_font(size=40):
    """מציאת פונט עברי מתאים"""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]
    
    for font_path in font_paths:
        try:
            if os.path.exists(font_path):
                logger.info(f"✅ Using font: {font_path}")
                return ImageFont.truetype(font_path, size)
        except Exception as e:
            logger.debug(f"❌ Could not load font {font_path}: {e}")
            continue
    
    logger.warning("⚠️ לא נמצא פונט TTF, משתמש בפונט ברירת מחדל")
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
    except:
        return ImageFont.load_default()

def wrap_text(text, font, max_width, draw):
    """
    חלוקת טקסט לשורות - תיקון הבעיה שגילינו!
    ✅ כשיש שורה אחת - צריך עיבוד
    ✅ כשיש 2+ שורות - עובד טוב
    """
    # ✅ עיבוד ראשוני של כל הטקסט
    hebrew_text = prepare_hebrew_text(text)
    
    # בדיקה אם הטקסט קצר מספיק לשורה אחת
    try:
        bbox = draw.textbbox((0, 0), hebrew_text, font=font)
        text_width = bbox[2] - bbox[0]
    except:
        text_width = draw.textsize(hebrew_text, font=font)[0]
    
    # ✅ אם זה שורה אחת - החזר ישירות עם עיבוד!
    if text_width <= max_width:
        return [hebrew_text]
    
    # חלוקה למילים
    words = hebrew_text.split()
    lines = []
    current_line = []
    
    for word in words:
        test_line = ' '.join(current_line + [word])
        try:
            bbox = draw.textbbox((0, 0), test_line, font=font)
            width = bbox[2] - bbox[0]
        except:
            width = draw.textsize(test_line, font=font)[0]
        
        if width <= max_width:
            current_line.append(word)
        else:
            if current_line:
                # ✅ עיבוד נוסף של כל שורה בנפרד!
                line_text = ' '.join(current_line)
                lines.append(prepare_hebrew_text(line_text))
            current_line = [word]
    
    if current_line:
        line_text = ' '.join(current_line)
        lines.append(prepare_hebrew_text(line_text))
    
    return lines

def make_text_image(text, width, height):
    """יצירת תמונה עם טקסט עברי - מחזירה RGB + יישור מימין"""
    # יצירת תמונה שקופה זמנית
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    font = get_font(size=36)
    
    max_text_width = int(width * 0.9)
    lines = wrap_text(text, font, max_text_width, draw)
    
    line_height = 45
    total_height = len(lines) * line_height
    y_start = (height - total_height) // 2
    
    for i, line in enumerate(lines):
        try:
            bbox = draw.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
        except:
            text_width, text_height = draw.textsize(line, font=font)
        
        # ✅ יישור מימין במקום ממרכז!
        x = width - text_width - 50  # 50 פיקסלים מהשוליים הימניים
        y = y_start + (i * line_height)
        
        padding = 12
        draw.rectangle(
            [x - padding, y - padding, x + text_width + padding, y + text_height + padding],
            fill=(0, 0, 0, 200)
        )
        
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))
    
    # המרה ל-RGB (3 ערוצים) על רקע שחור
    rgb_img = Image.new('RGB', (width, height), (0, 0, 0))
    rgb_img.paste(img, (0, 0), img)  # משתמש ב-alpha channel כמסכה
    
    return np.array(rgb_img)

def create_hebrew_subtitle_clip(text, start, duration, video_size):
    """יצירת קליפ כתובית עברית"""
    width, height = video_size
    subtitle_height = 150
    
    def make_frame(t):
        return make_text_image(text, width, subtitle_height)
    
    clip = VideoClip(make_frame, duration=duration)
    clip = clip.set_start(start)
    clip = clip.set_position(('center', height - subtitle_height - 20))
    
    return clip

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    video_path = None
    audio_path = None
    output_path = None
    video = None
    
    try:
        if update.message.video.file_size > 50 * 1024 * 1024:
            await update.message.reply_text("❌ הסרטון גדול מדי! מקסימום 50MB")
            return
        
        status_msg = await update.message.reply_text("⏳ מעבד את הסרטון...")
        
        video_file = await update.message.video.get_file()
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as temp_video:
            await video_file.download_to_drive(temp_video.name)
            video_path = temp_video.name
        
        logger.info(f"Video downloaded: {video_path}")
        
        await status_msg.edit_text("🎤 מחלץ אודיו...")
        
        video = VideoFileClip(video_path)
        
        if video.duration > 600:
            await update.message.reply_text("❌ הסרטון ארוך מדי! מקסימום 10 דקות")
            video.close()
            os.remove(video_path)
            return
        
        # בדיקה שיש אודיו
        if video.audio is None:
            await update.message.reply_text("❌ הסרטון לא מכיל אודיו!")
            video.close()
            os.remove(video_path)
            return
        
        audio_path = video_path.replace('.mp4', '.mp3')
        video.audio.write_audiofile(audio_path, verbose=False, logger=None)
        
        video_size = video.size
        logger.info(f"Video size: {video_size}")
        
        video.close()
        video = None
        gc.collect()
        
        await status_msg.edit_text("🗣️ מתמלל דיבור עם Groq...")
        
        result = transcribe_with_groq(audio_path)
        segments = result.get('segments', [])
        
        logger.info(f"Found {len(segments)} segments")
        
        if not segments:
            await update.message.reply_text("❌ לא נמצא דיבור באודיו")
            return
        
        gc.collect()
        
        await status_msg.edit_text("🌍 מתרגם לעברית...")
        
        translator = GoogleTranslator(source='en', target='iw')
        subtitles = []
        
        for seg in segments:
            text = seg.get('text', '').strip()
            if text and len(text) > 2:
                try:
                    translated = translator.translate(text)
                    subtitles.append({
                        'start': seg['start'],
                        'end': seg['end'],
                        'text': translated
                    })
                    logger.info(f"Translated: {text[:30]} -> {translated[:30]}")
                except Exception as e:
                    logger.error(f"Translation error: {e}")
                    continue
        
        if not subtitles:
            await update.message.reply_text("❌ לא נמצא טקסט לתרגום")
            return
        
        logger.info(f"Created {len(subtitles)} subtitles")
        
        await status_msg.edit_text("🎨 מוסיף כתוביות לסרטון...")
        
        video = VideoFileClip(video_path)
        
        txt_clips = []
        for i, sub in enumerate(subtitles):
            try:
                clip = create_hebrew_subtitle_clip(
                    sub['text'],
                    sub['start'],
                    sub['end'] - sub['start'],
                    video_size
                )
                txt_clips.append(clip)
                logger.info(f"Created subtitle clip {i+1}/{len(subtitles)}")
            except Exception as e:
                logger.error(f"Failed to create subtitle clip {i}: {e}")
                continue
        
        if not txt_clips:
            await update.message.reply_text("❌ נכשל ביצירת כתוביות")
            return
        
        logger.info(f"Compositing video with {len(txt_clips)} subtitle clips")
        
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
        
        logger.info("Video compositing complete")
        
        final_video.close()
        video.close()
        gc.collect()
        
        await status_msg.edit_text("📤 שולח את הסרטון...")
        
        with open(output_path, 'rb') as video_file_to_send:
            await update.message.reply_video(
                video=video_file_to_send,
                caption="✅ הנה הסרטון שלך עם כתוביות בעברית!\n⚡ Powered by Groq",
                read_timeout=60,
                write_timeout=60
            )
        
        await status_msg.delete()
        logger.info("Video sent successfully!")
        
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        try:
            await update.message.reply_text(f"❌ שגיאה: {str(e)}")
        except:
            pass
        
    finally:
        try:
            if video:
                video.close()
        except:
            pass
        
        for file_path in [video_path, audio_path, output_path]:
            try:
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"Cleaned up: {file_path}")
            except Exception as e:
                logger.error(f"Failed to delete {file_path}: {e}")
        
        gc.collect()

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
    
    logger.info("🤖 הבוט מתחיל לרוץ עם Groq...")
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    run_bot()
