#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
בוט טלגרם להוספת כתוביות מתורגמות
"""

import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import whisper
from googletrans import Translator
import asyncio
from pathlib import Path
import time

# הגדרת לוגים
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class SubtitleBot:
    def __init__(self):
        """אתחול הבוט"""
        logger.info("מאתחל את הבוט...")
        self.model = whisper.load_model("tiny")  # tiny למהירות
        self.translator = Translator()
        logger.info("הבוט מוכן!")
    
    def transcribe_video(self, video_path):
        """תמלול הסרטון"""
        logger.info(f"מתמלל: {video_path}")
        result = self.model.transcribe(video_path, language="en", verbose=False)
        logger.info(f"נמצאו {len(result['segments'])} קטעים")
        return result
    
    def translate_text(self, text):
        """תרגום לעברית"""
        for attempt in range(3):
            try:
                translation = self.translator.translate(text, src='en', dest='he')
                return translation.text
            except Exception as e:
                if attempt < 2:
                    time.sleep(1)
                else:
                    logger.warning(f"שגיאה בתרגום: {e}")
                    return text
    
    def format_time(self, seconds):
        """המרה לפורמט SRT"""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    
    def create_srt(self, segments, output_path):
        """יצירת קובץ כתוביות"""
        logger.info("מתרגם לעברית...")
        
        with open(output_path, 'w', encoding='utf-8') as f:
            for i, seg in enumerate(segments, 1):
                hebrew = self.translate_text(seg['text'].strip())
                start = self.format_time(seg['start'])
                end = self.format_time(seg['end'])
                
                f.write(f"{i}\n{start} --> {end}\n{hebrew}\n\n")
        
        logger.info(f"קובץ SRT נוצר: {output_path}")
    
    def add_subs_to_video(self, video_path, srt_path, output_path):
        """הוספת כתוביות לסרטון עם גופן עברי"""
        logger.info("מוסיף כתוביות לסרטון...")
        
        # נתיב לגופן העברי
        font_path = "גופנים/NotoSansHebrew-VariableFont_wdth,wght.ttf"
        
        # בדיקה אם הגופן קיים
        if not os.path.exists(font_path):
            logger.warning("גופן עברי לא נמצא, משתמש בגופן ברירת מחדל")
            font_path = None
        
        # בניית פקודת FFmpeg
        if font_path:
            # עם גופן עברי מותאם אישית
            srt_escaped = srt_path.replace('\\', '/').replace(':', '\\:')
            font_escaped = font_path.replace('\\', '/').replace(':', '\\:')
            
            cmd = (
                f"ffmpeg -i '{video_path}' "
                f"-vf \"subtitles='{srt_escaped}':fontsdir='גופנים':force_style='"
                f"FontName=Noto Sans Hebrew,"
                f"FontSize=20,"
                f"PrimaryColour=&HFFFFFF&,"
                f"OutlineColour=&H000000&,"
                f"BorderStyle=3,"
                f"Outline=2,"
                f"Shadow=1,"
                f"Bold=1,"
                f"MarginV=30'\" "
                f"-c:a copy '{output_path}' -y -loglevel error"
            )
        else:
            # ללא גופן מותאם (ברירת מחדל)
            cmd = (
                f"ffmpeg -i '{video_path}' "
                f"-vf \"subtitles='{srt_path}':force_style='FontSize=20,PrimaryColour=&HFFFFFF&,Bold=1'\" "
                f"-c:a copy '{output_path}' -y -loglevel error"
            )
        
        result = os.system(cmd)
        
        if result == 0:
            logger.info(f"סרטון מוכן: {output_path}")
            return True
        else:
            logger.error("שגיאה בהוספת כתוביות")
            return False

# יצירת מופע גלובלי של הבוט
subtitle_bot = SubtitleBot()

# פונקציות הטלגרם
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """פקודת /start"""
    welcome_text = """
🎬 *בוט כתוביות מתורגמות*

ברוכים הבאים! 👋

*איך זה עובד?*
1️⃣ שלח לי סרטון (עד 50MB)
2️⃣ אני אתמלל את האנגלית
3️⃣ אתרגם לעברית
4️⃣ אשלח לך סרטון + קובץ SRT

*הערות חשובות:*
⚡ העיבוד לוקח 2-5 דקות
📱 סרטונים ארוכים מדי עלולים לכשל
🌐 צריך חיבור אינטרנט טוב

*פקודות:*
/start - הודעת פתיחה
/help - עזרה

שלח סרטון כדי להתחיל! 🚀
    """
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """פקודת /help"""
    help_text = """
❓ *עזרה*

*איך משתמשים?*
פשוט שלח סרטון לבוט!

*מה הגבלות הגודל?*
עד 50MB (הגבלת טלגרם)

*כמה זמן זה לוקח?*
• סרטון של 1 דקה: ~2 דקות
• סרטון של 5 דקות: ~5 דקות

*מה עושים אם יש שגיאה?*
נסה סרטון קטן יותר או פנה אלי

*פורמטים נתמכים:*
MP4, MOV, AVI, MKV

צריך עזרה נוספת? שלח הודעה! 💬
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """טיפול בסרטון שנשלח"""
    video = update.message.video
    
    # בדיקת גודל
    if video.file_size > 50 * 1024 * 1024:  # 50MB
        await update.message.reply_text(
            "❌ הסרטון גדול מדי! (מקסימום 50MB)\n"
            "נסה לדחוס אותו או לשלוח סרטון קצר יותר."
        )
        return
    
    # הודעת התחלה
    status_msg = await update.message.reply_text(
        "⏳ *מקבל את הסרטון...*",
        parse_mode='Markdown'
    )
    
    try:
        # הורדת הסרטון
        file = await context.bot.get_file(video.file_id)
        video_path = f"downloads/{video.file_id}.mp4"
        os.makedirs("downloads", exist_ok=True)
        os.makedirs("output", exist_ok=True)
        
        await file.download_to_drive(video_path)
        
        # תמלול
        await status_msg.edit_text("🎤 *מתמלל את האודיאו...*", parse_mode='Markdown')
        result = subtitle_bot.transcribe_video(video_path)
        
        # תרגום
        await status_msg.edit_text(
            f"📝 *מתרגם {len(result['segments'])} קטעים לעברית...*",
            parse_mode='Markdown'
        )
        srt_path = f"output/{video.file_id}.srt"
        subtitle_bot.create_srt(result['segments'], srt_path)
        
        # הוספה לסרטון
        await status_msg.edit_text("🎥 *מוסיף כתוביות לסרטון...*", parse_mode='Markdown')
        output_video = f"output/{video.file_id}_hebrew.mp4"
        success = subtitle_bot.add_subs_to_video(video_path, srt_path, output_video)
        
        if not success:
            raise Exception("Failed to add subtitles")
        
        # שליחת התוצאות
        await status_msg.edit_text("📤 *שולח את הקבצים...*", parse_mode='Markdown')
        
        # שליחת הסרטון
        with open(output_video, 'rb') as video_file:
            await update.message.reply_video(
                video=video_file,
                caption="✅ *הסרטון עם כתוביות בעברית!*",
                parse_mode='Markdown'
            )
        
        # שליחת קובץ SRT
        with open(srt_path, 'rb') as srt_file:
            await update.message.reply_document(
                document=srt_file,
                filename="hebrew_subtitles.srt",
                caption="📄 *קובץ הכתוביות (SRT)*",
                parse_mode='Markdown'
            )
        
        await status_msg.delete()
        
        # ניקוי
        os.remove(video_path)
        os.remove(output_video)
        os.remove(srt_path)
        
    except Exception as e:
        logger.error(f"שגיאה בעיבוד: {e}")
        await status_msg.edit_text(
            "❌ *אופס! משהו השתבש*\n\n"
            "נסה:\n"
            "• סרטון קטן יותר\n"
            "• פורמט אחר\n"
            "• לשלוח שוב\n\n"
            f"שגיאה טכנית: `{str(e)[:100]}`",
            parse_mode='Markdown'
        )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """טיפול בקובץ שנשלח כמסמך"""
    await update.message.reply_text(
        "💡 *טיפ*: שלח את הסרטון כסרטון (לא כקובץ)\n\n"
        "לחץ על 📎 בטלגרם ובחר 'וידאו' במקום 'קובץ'",
        parse_mode='Markdown'
    )

def main():
    """הפעלת הבוט"""
    # קבלת ה-TOKEN מ-Environment Variable
    TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN לא הוגדר!")
        return
    
    # יצירת האפליקציה
    application = Application.builder().token(TOKEN).build()
    
    # הוספת handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.VIDEO, handle_video))
    application.add_handler(MessageHandler(filters.Document.VIDEO, handle_document))
    
    # הפעלת הבוט
    logger.info("🚀 הבוט פועל!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
