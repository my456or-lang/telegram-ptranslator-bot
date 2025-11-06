# Video Subtitle Bot (English -> Hebrew)

This repository contains a Telegram bot that:
- Receives a video (up to 50MB, up to 10 min)
- Uses Groq Whisper to transcribe (English)
- Translates segments to Hebrew
- Burns Hebrew subtitles into the video and returns it to the user

## Setup
1. Download / clone the repo.
2. Put a Hebrew font in `fonts/NotoSansHebrew-Regular.ttf`.
3. Create a GitHub repo and push these files.
4. Deploy to Render (see deployment instructions).

## Environment variables (Render)
- TELEGRAM_BOT_TOKEN = your Telegram bot token (from @BotFather)
- GROQ_API_KEY = your Groq API key

## Requirements
See `requirements.txt`.

## Notes
- If Hebrew appears reversed or not readable, we attempt a reverse string; if issues persist try different Hebrew font.
