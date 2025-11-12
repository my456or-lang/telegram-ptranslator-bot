import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from deep_translator import GoogleTranslator
from moviepy.editor import VideoFileClip, CompositeVideoClip, ImageClip
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

def prepare_hebrew_text(text):
    try:
        reshaped_text = arabic_reshaper.reshape(text)
        bidi_text = get_display(reshaped_text)
        return bidi_text
    except Exception as e:
        logger.warning(f"Failed to prepare Hebrew text: {e}")
        return text

def get_font(size=40):
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    for font_path in font_paths:
        if os.path.exists(font_path):
            return ImageFont.truetype(font_path, size)
    return ImageFont.load_default()

def wrap_text(text, font, max_width, draw):
    words = text.split()
    lines, current_line = [], []
    for word in words:
        test_line = ' '.join(current_line + [word])
        width = draw.textlength(test_line, font=font)
        if width <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
            current_line = [word]
    if current_line:
        lines.append(' '.join(current_line))
    return lines

def make_text_image_outline(text, width, height):
    """יוצר תמונה עם טקסט לבן ומסגרת שחורה, רקע שקוף"""
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    hebrew_text = prepare_hebrew_text(text)
    font = get_font(size=42)
    max_text_width = int(width * 0.9)
    lines = wrap_text(hebrew_text, font, max_text_width, draw)

    line_height = 55
    total_height = len(lines) * line_height
    y_start = (height - total_height) // 2

    for i, line in enumerate(lines):
        text_width = draw.textlength(line, font=font)
        x = (width - int(text_width)) // 2
        y = y_start + (i * line_height)

        # ציור outline שחור עבה
        for dx in [-2, -1, 0, 1, 2]:
            for dy in [-2, -1, 0, 1, 2]:
                draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0, 255))

        # טקסט לבן
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))
    return np.array(img, dtype=np.uint8)

def create_hebrew_subtitle_clip(text, start, duration, video_size):
    width, height = video_size
    subtitle_height = 160
    rgba = make_text_image_outline(text, width, subtitle_height)
    rgb = rgba[:, :, :3]
    alpha = rgba[:, :, 3]
    img_clip = ImageClip(rgb).set_duration(duration).set_start(start)
    mask = ImageClip(alpha, ismask=True).set_duration(duration).set_start(start)
    img_clip = img_clip.set_mask(mask)
    img_clip = img_clip.set_position(('center', height - subtitle_height - 40))
    return img_clip

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    video_path = audio_path = output_path = None
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
        
        await status_msg.edit_text("🎤 מחלץ אודיו...")
        video = VideoFileClip(video_path)
        if video.duration > 600:
            await update.message.reply_text("❌ הסרטון ארוך מדי! מקסימום 10 דקות")
            return
        audio_path = video_path.replace('.mp4', '.mp3')
        video.audio.write_audiofile(audio_path, verbose=False, logger=None)
        video_size = video.size
        video.close(); video = None; gc.collect()

        await status_msg.edit_text("🗣️ מתמלל עם Groq...")
        result = transcribe_with_groq(audio_path)
        segments = result.get('segments', [])
        if not segments:
            await update.message.reply_text("❌ לא נמצא דיבור באודיו")
            return
        
        await status_msg.edit_text("🌍 מתרגם לעברית...")
        translator = GoogleTranslator(source='en', target='iw')
        subtitles = []
        for seg in segments:
            text = seg.get('text', '').strip()
            if text:
                translated = translator.translate(text)
                subtitles.append({
                    'start': seg['start'],
                    'end': seg['end'],
                    'text': translated
                })
        
        await status_msg.edit_text("🎨 מוסיף כתוביות שקופות...")
        video = VideoFileClip(video_path)
        txt_clips = [
            create_hebrew_subtitle_clip(sub['text'], sub['start'], sub['end'] - sub['start'], video_size)
            for sub in subtitles
        ]
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

        final_video.close(); video.close(); gc.collect()
        await status_msg.edit_text("📤 שולח את הסרטון...")
        with open(output_path, 'rb') as f:
            await update.message.reply_video(
                video=f,
                caption="✅ הנה הסרטון שלך עם כתוביות בעברית שקופות!\n⚡ Powered by Groq",
            )
        await status_msg.delete()
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        await update.message.reply_text(f"❌ שגיאה: {e}")
    finally:
        for p in [video_path, audio_path, output_path]:
            if p and os.path.exists(p):
                os.remove(p)
        gc.collect()

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception: {context.error}", exc_info=context.error)

def run_bot():
    TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
    GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
    if not TOKEN or not GROQ_API_KEY:
        logger.error("❌ חסרים מפתחות סביבה (TELEGRAM_BOT_TOKEN או GROQ_API_KEY)")
        return
    
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.VIDEO, handle_video))
    application.add_error_handler(error_handler)
    logger.info("🤖 הבוט פועל עם Groq...")
    application.run_polling(drop_pending_updates=True)

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    Thread(target=run_flask, daemon=True).start()
    run_bot()
