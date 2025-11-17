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
import math

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# נתיב לגופן העברי שלך
HEBREW_FONT_PATH = "/app/fonts/NotoSansHebrew-VariableFont_wdth,wght.ttf"

# הגדרות פיצול
MAX_SEGMENT_DURATION = 240  # 4 דקות לכל חלק
MAX_FILE_SIZE = 18 * 1024 * 1024  # 18MB (נשאיר מרווח בטיחות)

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
        "✨ חדש! הבוט מפצל אוטומטית סרטונים ארוכים:\n"
        "• סרטון עד 20 דקות\n"
        "• גודל עד 50MB בכניסה\n"
        "• מחלק לחלקים של 4 דקות\n\n"
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
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    try:
        if os.path.exists(HEBREW_FONT_PATH):
            font = ImageFont.truetype(HEBREW_FONT_PATH, 38)
        else:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 38)
    except Exception as e:
        logger.error(f"❌ Failed to load font: {e}")
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 38)
    
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
    
    line_height = 50
    total_height = len(lines) * line_height
    y_start = height - total_height - 10
    
    for i, line in enumerate(lines):
        try:
            bbox = draw.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
        except:
            text_width, text_height = draw.textsize(line, font=font)[0:2]
        
        x = (width - text_width) // 2
        y = y_start + (i * line_height)
        
        padding = 8
        draw.rectangle(
            [x - padding, y - padding, x + text_width + padding, y + text_height + padding],
            fill=(40, 35, 20, 150)
        )
        
        outline_width = 3
        for adj_x in range(-outline_width, outline_width + 1):
            for adj_y in range(-outline_width, outline_width + 1):
                if adj_x != 0 or adj_y != 0:
                    draw.text((x + adj_x, y + adj_y), line, font=font, fill=(0, 0, 0, 255))
        
        draw.text((x, y), line, font=font, fill=(255, 255, 230, 255))
    
    rgb_img = Image.new('RGB', (width, height), (0, 0, 0))
    r, g, b, a = img.split()
    rgb_img.paste(img, (0, 0), a)
    
    return np.array(rgb_img)

def create_subtitle_clip(text, start, duration, video_size):
    """יצירת קליפ כתובית עם איחור של 1.8 שניות"""
    width, height = video_size
    subtitle_height = 100
    
    def make_frame(t):
        return create_subtitle_image(text, width, subtitle_height)
    
    clip = VideoClip(make_frame, duration=duration)
    clip = clip.set_start(start + 1.8)
    clip = clip.set_position(('center', height - subtitle_height - 10))
    
    return clip

def process_video_segment(video_path, start_time, end_time, segment_num, total_segments, status_msg, update):
    """עיבוד חלק בודד של סרטון"""
    output_path = None
    video = None
    final_video = None
    audio_path = None
    
    try:
        logger.info(f"🎬 Processing segment {segment_num}/{total_segments}: {start_time:.1f}s - {end_time:.1f}s")
        
        # פתיחת הסרטון וחיתוך החלק הרלוונטי
        video = VideoFileClip(video_path).subclip(start_time, end_time)
        
        if video.audio is None:
            logger.warning(f"⚠️ No audio in segment {segment_num}")
            return None
        
        # חילוץ אודיו מהחלק
        audio_path = video_path.replace('.mp4', f'_segment{segment_num}.mp3')
        video.audio.write_audiofile(audio_path, verbose=False, logger=None)
        
        video_size = video.size
        
        # תמלול
        result = transcribe_with_groq(audio_path)
        segments = result.get('segments', [])
        
        if not segments:
            logger.warning(f"⚠️ No speech in segment {segment_num}")
            video.close()
            return None
        
        # תרגום
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
                except Exception as e:
                    logger.error(f"Translation error: {e}")
                    continue
        
        if not subtitles:
            logger.warning(f"⚠️ No subtitles for segment {segment_num}")
            video.close()
            return None
        
        # יצירת כתוביות
        txt_clips = []
        for sub in subtitles:
            try:
                clip = create_subtitle_clip(
                    sub['text'],
                    sub['start'],
                    sub['end'] - sub['start'],
                    video_size
                )
                txt_clips.append(clip)
            except Exception as e:
                logger.error(f"Failed subtitle: {e}")
                continue
        
        if not txt_clips:
            logger.warning(f"⚠️ No subtitle clips for segment {segment_num}")
            video.close()
            return None
        
        # שילוב
        final_video = CompositeVideoClip([video] + txt_clips)
        output_path = video_path.replace('.mp4', f'_sub_part{segment_num}.mp4')
        
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
        
        # מחיקת אודיו זמני
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)
        
        gc.collect()
        
        return output_path
        
    except Exception as e:
        logger.error(f"Error processing segment {segment_num}: {e}")
        if final_video:
            final_video.close()
        if video:
            video.close()
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)
        return None

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    video_path = None
    temp_files = []
    
    try:
        file_size_mb = update.message.video.file_size / (1024 * 1024)
        
        # בדיקה ראשונית
        if update.message.video.file_size > 50 * 1024 * 1024:
            await update.message.reply_text(
                f"❌ הסרטון גדול מדי ({file_size_mb:.1f}MB)!\n\n"
                "📊 מקסימום: 50MB\n"
                "אנא דחוס את הסרטון ונסה שוב."
            )
            return
        
        logger.info(f"📦 Received video: {file_size_mb:.2f}MB")
        status_msg = await update.message.reply_text("⏳ מוריד את הסרטון...")
        
        try:
            video_file = await update.message.video.get_file()
        except Exception as e:
            if "File is too big" in str(e):
                await update.message.reply_text("❌ הקובץ גדול מדי עבור Telegram Bot API (מקסימום 20MB להורדה)")
            else:
                await update.message.reply_text(f"❌ שגיאה: {str(e)}")
            return
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as temp_video:
            await video_file.download_to_drive(temp_video.name)
            video_path = temp_video.name
            temp_files.append(video_path)
        
        # בדיקת אורך הסרטון
        video = VideoFileClip(video_path)
        duration = video.duration
        video.close()
        
        logger.info(f"⏱️ Video duration: {duration:.1f}s ({duration/60:.1f} minutes)")
        
        if duration > 1200:  # 20 דקות
            await update.message.reply_text(
                f"❌ הסרטון ארוך מדי ({duration/60:.1f} דקות)!\n\n"
                "⏱️ מקסימום: 20 דקות"
            )
            return
        
        # חישוב מספר חלקים
        num_segments = math.ceil(duration / MAX_SEGMENT_DURATION)
        
        if num_segments == 1:
            await status_msg.edit_text("🎬 מעבד סרטון קצר...")
        else:
            await status_msg.edit_text(
                f"📊 מפצל לחלקים...\n"
                f"🎬 {num_segments} חלקים של ~{MAX_SEGMENT_DURATION/60:.0f} דקות\n"
                f"⏳ זה ייקח זמן..."
            )
        
        logger.info(f"📊 Splitting into {num_segments} segments")
        
        # עיבוד כל חלק
        output_videos = []
        
        for i in range(num_segments):
            start_time = i * MAX_SEGMENT_DURATION
            end_time = min((i + 1) * MAX_SEGMENT_DURATION, duration)
            
            try:
                await status_msg.edit_text(
                    f"🎨 מעבד חלק {i+1}/{num_segments}...\n"
                    f"⏱️ {start_time/60:.1f}-{end_time/60:.1f} דקות\n"
                    f"🗣️ מתמלל ומתרגם..."
                )
            except:
                pass
            
            output = process_video_segment(
                video_path, start_time, end_time, 
                i+1, num_segments, status_msg, update
            )
            
            if output:
                output_videos.append(output)
                temp_files.append(output)
        
        if not output_videos:
            await update.message.reply_text("❌ לא הצלחתי לעבד את הסרטון")
            return
        
        # שליחת כל החלקים
        await status_msg.edit_text(f"📤 שולח {len(output_videos)} חלקים...")
        
        for idx, output_path in enumerate(output_videos, 1):
            try:
                file_size = os.path.getsize(output_path)
                output_size_mb = file_size / (1024 * 1024)
                
                if file_size > 50 * 1024 * 1024:
                    await update.message.reply_text(
                        f"⚠️ חלק {idx} גדול מדי ({output_size_mb:.1f}MB) - מדלג"
                    )
                    continue
                
                with open(output_path, 'rb') as f:
                    caption = (
                        f"✅ חלק {idx}/{len(output_videos)}\n"
                        f"📦 {output_size_mb:.1f}MB\n"
                        f"⚡ Powered by Groq"
                    )
                    
                    await update.message.reply_video(
                        video=f,
                        caption=caption,
                        read_timeout=180,
                        write_timeout=180,
                        connect_timeout=90
                    )
                
                logger.info(f"✅ Sent part {idx}/{len(output_videos)}")
                
            except Exception as e:
                logger.error(f"Failed to send part {idx}: {e}")
                await update.message.reply_text(f"❌ שגיאה בשליחת חלק {idx}")
        
        await status_msg.delete()
        await update.message.reply_text(
            f"🎉 הושלם!\n"
            f"נשלחו {len(output_videos)} חלקים בהצלחה"
        )
        logger.info("✅ All parts sent successfully!")
        
    except Exception as e:
        logger.error(f"❌ ERROR: {e}", exc_info=True)
        try:
            await update.message.reply_text(f"❌ שגיאה: {str(e)[:200]}")
        except:
            pass
    
    finally:
        logger.info("🧹 Cleaning up...")
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
    
    if os.path.exists(HEBREW_FONT_PATH):
        logger.info(f"✅ Hebrew font loaded: {HEBREW_FONT_PATH}")
    else:
        logger.warning(f"⚠️ Hebrew font not found at: {HEBREW_FONT_PATH}")
    
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.VIDEO, handle_video))
    application.add_error_handler(error_handler)
    
    logger.info("🤖 Bot starting with auto-split support...")
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
