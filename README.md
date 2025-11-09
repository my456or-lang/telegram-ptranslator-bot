# 🤖 בוט טלגרם לכתוביות מתורגמות

בוט שמקבל סרטון באנגלית ומחזיר אותו עם כתוביות בעברית.

## 🚀 תכונות

- ✅ תמלול אוטומטי באנגלית (Whisper AI)
- ✅ תרגום אוטומטי לעברית
- ✅ הוספת כתוביות ישירות לסרטון
- ✅ שליחת קובץ SRT נפרד
- ✅ ממשק פשוט בטלגרם

## 📱 איך להשתמש

1. פתח את הבוט בטלגרם
2. שלח את פקודת `/start`
3. שלח סרטון (עד 50MB)
4. המתן 2-5 דקות
5. קבל את הסרטון עם כתוביות + קובץ SRT

## 🔧 הרצה מקומית

### דרישות מוקדמות
- Python 3.8+
- FFmpeg

### התקנה
```bash
# שכפול הפרויקט
git clone https://github.com/YOUR_USERNAME/telegram-subtitle-bot.git
cd telegram-subtitle-bot

# התקנת תלויות
pip install -r requirements.txt

# הגדרת TOKEN
export TELEGRAM_BOT_TOKEN="your_token_here"

# הפעלת הבוט
python bot.py
```

## ☁️ Deploy ל-Render (חינמי)

### שלב 1: צור בוט בטלגרם
1. פתח [@BotFather](https://t.me/BotFather) בטלגרם
2. שלח `/newbot`
3. עקוב אחרי ההוראות
4. שמור את ה-TOKEN

### שלב 2: Deploy ל-Render
1. צור חשבון ב-[Render](https://render.com)
2. לחץ **New +** → **Web Service**
3. חבר את ה-GitHub repository
4. הגדרות:
   - **Environment**: Python 3
   - **Build Command**: `apt-get update && apt-get install -y ffmpeg && pip install -r requirements.txt`
   - **Start Command**: `python bot.py`
   - **Instance Type**: Free

### שלב 3: הוסף Environment Variable
1. ב-Render Dashboard, עבור ל-Environment
2. הוסף משתנה:
   - **Key**: `TELEGRAM_BOT_TOKEN`
   - **Value**: ה-TOKEN שקיבלת מ-BotFather
3. שמור ו-Deploy

## 📊 הגבלות

- **גודל סרטון**: עד 50MB (הגבלת טלגרם)
- **זמן עיבוד**: 2-5 דקות (תלוי באורך הסרטון)
- **Render Free Tier**: 750 שעות חינם בחודש

## 🎨 התאמה אישית

### שינוי מודל Whisper
בקובץ `bot.py`, שורה 27:
```python
self.model = whisper.load_model("base")  # אפשרויות: tiny, base, small, medium, large
```

### שינוי עיצוב כתוביות
בקובץ `bot.py`, שורה 81:
```python
force_style='FontSize=24,PrimaryColour=&HFFFFFF&,OutlineColour=&H000000&'
```

## 🔧 פתרון בעיות

### הבוט לא עונה
1. בדוק את ה-Logs ב-Render Dashboard
2. וודא שה-TOKEN נכון
3. נסה Restart את השירות

### "Out of memory"
- השתמש במודל `tiny` במקום `base`
- הגבל את גודל הסרטונים

### תרגום לא עובד
- וודא חיבור אינטרנט
- נסה שוב (Google Translate לפעמים מגביל)

## 📝 פורמטים נתמכים

- MP4
- MOV
- AVI
- MKV
- FLV

## 🤝 תרומה

Pull requests מתקבלים בברכה! אם יש רעיון לשיפור:

1. Fork את הפרויקט
2. צור branch חדש (`git checkout -b feature/amazing-feature`)
3. Commit את השינויים (`git commit -m 'Add amazing feature'`)
4. Push ל-branch (`git push origin feature/amazing-feature`)
5. פתח Pull Request

## 📄 רישיון

MIT License - ראה קובץ LICENSE לפרטים

## 🔗 קישורים

- [OpenAI Whisper](https://github.com/openai/whisper)
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
- [Render Documentation](https://render.com/docs)

## 💡 תכונות עתידיות

- [ ] תמיכה בשפות נוספות
- [ ] בחירת עיצוב כתוביות
- [ ] עיבוד אצווה של מספר סרטונים
- [ ] שמירת היסטוריית משתמשים
- [ ] סטטיסטיקות שימוש

## 📧 יצירת קשר

יש שאלות? פתח [Issue](https://github.com/YOUR_USERNAME/telegram-subtitle-bot/issues) או שלח הודעה לבוט!

---

**נוצר עם ❤️ באמצעות Claude**
