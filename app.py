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

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# נתיב לגופן העברי שלך
HEBREW_FONT_PATH = "/app/fonts/NotoSansHebrew-VariableFont_wdth,wght.ttf"

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
        "⚡ כתוביות מקצועיות עם רקע מעומעם!"
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

def create_subtitle_image(text, width, height):
    """יצירת תמונה עם טקסט עברי ורקע מעומעם צהבהב"""
    # יצירת תמונה שקופה
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # טעינת הגופן העברי - גופן קטן יותר
    try:
        if os.path.exists(HEBREW_FONT_PATH):
            font = ImageFont.truetype(HEBREW_FONT_PATH, 38)  # הקטנה מ-50 ל-38
            logger.info(f"✅ Loaded Hebrew font: {HEBREW_FONT_PATH}")
        else:
            logger.warning(f"⚠️ Font not found at {HEBREW_FONT_PATH}, using fallback")
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 38)
    except Exception as e:
        logger.error(f"❌ Failed to load font: {e}")
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 38)
    
    # חלוקת הטקסט לשורות אם ארוך מדי
    max_width = width - 100
    words = text.split()
    lines = []
    current_line = []
    
    for word in words:
        test_line = ' '.join(current_line + [word])
        try:
            bbox = draw.textbbox((0, 0), test_line, font=font)
            line_width = bbox[2] - bbox[0]
        except:
            line_width = draw.textsize(test_line, font=font)[0]
        
        if line_width <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
            current_line = [word]
    
    if current_line:
        lines.append(' '.join(current_line))
    
    # חישוב גובה כולל
    line_height = 50  # הקטנה מ-65 ל-50
    total_height = len(lines) * line_height
    y_start = height - total_height - 10
    
    # ציור כל שורה
    for i, line in enumerate(lines):
        try:
            bbox = draw.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
        except:
            text_width, text_height = draw.textsize(line, font=font)[0:2]
        
        x = (width - text_width) // 2
        y = y_start + (i * line_height)
        
        # רקע מעומעם בגוון צהבהב-שחור (כמו בסרטים!)
        padding = 8
        # צבע: שחור עם גוון צהוב קל (R=40, G=35, B=20) ושקיפות 150
        draw.rectangle(
            [x - padding, y - padding, x + text_width + padding, y + text_height + padding],
            fill=(40, 35, 20, 150)  # צהבהב כהה עם שקיפות
        )
        
        # מתאר שחור (3 פיקסלים - קצת יותר דק)
        outline_width = 3
        for adj_x in range(-outline_width, outline_width + 1):
            for adj_y in range(-outline_width, outline_width + 1):
                if adj_x != 0 or adj_y != 0:
                    draw.text((x + adj_x, y + adj_y), line, font=font, fill=(0, 0, 0, 255))
        
        # הטקסט הצהבהב-לבן (כמו בסרטים!)
        draw.text((x, y), line, font=font, fill=(255, 255, 230, 255))  # לבן-צהבהב
    
    # המרה ל-RGB
    rgb_img = Image.new('RGB', (width, height), (0, 0, 0))
    r, g, b, a = img.split()
    rgb_img.paste(img, (0, 0), a)
    
    return np.array(rgb_img)

def create_subtitle_clip(text, start, duration, video_size):
    """יצירת קליפ כתובית עם איחור של 1.8 שניות"""
    width, height = video_size
    subtitle_height = 100  # הקטנה מ-130 ל-100
    
    def make_frame(t):
        return create_subtitle_image(text, width, subtitle_height)
    
    clip = VideoClip(make_frame, duration=duration)
    # הוספת איחור של 1.8 שניות
    clip = clip.set_start(start + 1.8)
    clip = clip.set_position(('center', height - subtitle_height - 10))
    
    return clip

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    video_path = None
    audio_path = None
    output_path = None
    video = None
    final_video = None
    
    try:
        # בדיקת גודל - הגדלה ל-50MB
        if update.message.video.file_size > 50 * 1024 * 1024:
            await update.message.reply_text("❌ הסרטון גדול מדי! מקסימום 50MB")
            return
        
        status_msg = await update.message.reply_text("⏳ מעבד את הסרטון...")
        
        # הורדת הסרטון
        video_file = await update.message.video.get_file()
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as temp_video:
            await video_file.download_to_drive(temp_video.name)
            video_path = temp_video.name
        
        logger.info(f"✅ Video downloaded: {video_path}")
        
        # פתיחת הסרטון
        await status_msg.edit_text("🎤 מחלץ אודיו...")
        video = VideoFileClip(video_path)
        
        # בדיקת אורך - הגדלה ל-10 דקות
        if video.duration > 600:  # 10 דקות
            await update.message.reply_text("❌ הסרטון ארוך מדי! מקסימום 10 דקות")
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
        logger.info(f"📐 Video size: {video_size}")
        
        # שחרור הסרטון זמנית
        video.close()
        video = None
        gc.collect()
        
        # תמלול עם Groq
        await status_msg.edit_text("🗣️ מתמלל דיבור...")
        result = transcribe_with_groq(audio_path)
        segments = result.get('segments', [])
        
        logger.info(f"📝 Found {len(segments)} segments")
        
        if not segments:
            await update.message.reply_text("❌ לא נמצא דיבור באודיו")
            return
        
        # תרגום
        await status_msg.edit_text("🌍 מתרגם לעברית...")
        translator = GoogleTranslator(source='en', target='iw')
        
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
                    logger.info(f"✅ {i+1}/{len(segments)}: {translated[:30]}...")
                except Exception as e:
                    logger.error(f"❌ Translation error: {e}")
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
        txt_clips = []
        for i, sub in enumerate(subtitles):
            try:
                clip = create_subtitle_clip(
                    sub['text'],
                    sub['start'],
                    sub['end'] - sub['start'],
                    video_size
                )
                txt_clips.append(clip)
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
        
        if not txt_clips:
            await update.message.reply_text("❌ נכשל ביצירת כתוביות")
            video.close()
            return
        
        logger.info(f"✅ Created {len(txt_clips)} subtitle clips")
        
        # שילוב הסרטון עם הכתוביות
        await status_msg.edit_text("🎬 מרכיב את הסרטון הסופי...")
        
        final_video = CompositeVideoClip([video] + txt_clips)
        output_path = video_path.replace('.mp4', '_sub.mp4')
        
        # כתיבת הסרטון
        final_video.write_videofile(
            output_path,
            codec='libx264',
            audio_codec='aac',
            preset='ultrafast',
            threads=2,
            verbose=False,
            logger=None
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
        temp_files = [video_path, audio_path, output_path]
        
        for file_path in temp_files:
            try:
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"🗑️ Deleted: {file_path}")
            except Exception as e:
                logger.error(f"Failed to delete {file_path}: {e}")
        
        gc.collect()
        logger.info("✅ Cleanup complete")

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
    
    # בדיקה שהגופן קיים
    if os.path.exists(HEBREW_FONT_PATH):
        logger.info(f"✅ Hebrew font loaded: {HEBREW_FONT_PATH}")
    else:
        logger.warning(f"⚠️ Hebrew font not found at: {HEBREW_FONT_PATH}")
    
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.VIDEO, handle_video))
    application.add_error_handler(error_handler)
    
    logger.info("🤖 Bot starting with Groq and Noto Sans Hebrew...")
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
