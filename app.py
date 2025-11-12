import os
import tempfile
import requests
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
from flask import Flask, request
from googletrans import Translator
import arabic_reshaper
from bidi.algorithm import get_display

# הגדרות Flask
app = Flask(__name__)

# אתחול מתרגם
translator = Translator()

# פונקציה לתרגום ויצירת כתוביות
def add_subtitle_to_video(video_path, translated_text):
    # עיבוד טקסט עברי/ערבי כדי שיוצג נכון
    reshaped_text = arabic_reshaper.reshape(translated_text)
    bidi_text = get_display(reshaped_text)

    # טעינת הסרטון
    clip = VideoFileClip(video_path)

    # יצירת כתובית — רקע שחור אטום, כיוון RTL, טקסט לבן
    subtitle = (
        TextClip(
            txt=bidi_text,
            fontsize=60,
            color="white",
            font="Arial-Bold",
            size=(clip.w, 150),
            method="caption",
            align="center",
            bg_color="black"  # רקע אטום (לא שקוף)
        )
        .set_position(("center", clip.h - 200))
        .set_duration(clip.duration)
    )

    # שילוב הכתובית עם הווידאו
    final = CompositeVideoClip([clip, subtitle])

    # שמירת הווידאו החדש לקובץ זמני
    output_path = tempfile.mktemp(suffix=".mp4")
    final.write_videofile(output_path, codec="libx264", audio_codec="aac")

    return output_path

# דוגמה לנתיב בדיקה (API)
@app.route("/translate_video", methods=["POST"])
def translate_video():
    try:
        video_url = request.json.get("video_url")
        target_lang = request.json.get("target_lang", "he")

        # הורדת הווידאו לקובץ זמני
        video_data = requests.get(video_url).content
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_video:
            temp_video.write(video_data)
            video_path = temp_video.name

        # תרגום טקסט לדוגמה (ניתן לשנות לפי שימוש אמיתי)
        translated_text = translator.translate("Hello world", dest=target_lang).text

        # יצירת וידאו עם כתוביות
        output_path = add_subtitle_to_video(video_path, translated_text)

        # העלאת הווידאו או החזרתו לפי הצורך
        return {"status": "success", "output_path": output_path}

    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
