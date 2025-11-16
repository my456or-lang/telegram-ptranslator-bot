# Telegram Subtitle Bot (Groq Whisper + burn SRT)

דרישות סביבת ריצה:
- Docker / Render / כל שרת שמריץ Docker
- משתני סביבה: `TELEGRAM_TOKEN`, `GROQ_API_KEY`, `PORT=8080`

התקנה והרצה (Docker):
```bash
docker build -t tg-subtitles .
docker run -e TELEGRAM_TOKEN=xxx -e GROQ_API_KEY=yyy -p 8080:8080 tg-subtitles
