# 🎬 Telegram Subtitle Bot (Groq Whisper + Hebrew Translation)

בוט טלגרם שמתרגם **אוטומטית כתוביות מאנגלית לעברית** על גבי סרטונים.
מבוסס על:
- 🧠 Whisper דרך Groq API לתמלול מהיר
- 🌍 Google Translator לתרגום לעברית
- 🎨 MoviePy + Pillow להוספת כתוביות מעוצבות
- 🐳 Docker ו-Flask להרצה נוחה בענן

---

## 🚀 הפעלה מקומית (ללא Docker)

1. צור קובץ `.env` לפי `.env.example`  
   והזן את:
   ```bash
   TELEGRAM_BOT_TOKEN=...
   GROQ_API_KEY=...
