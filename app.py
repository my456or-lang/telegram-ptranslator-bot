from flask import Flask, request, jsonify
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
from deep_translator import GoogleTranslator
from bidi.algorithm import get_display
import arabic_reshaper
import os
import imageio_ffmpeg

app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Translation video bot is running."

@app.route('/process', methods=['POST'])
def process_video():
    data = request.json
    video_url = data.get('video_url')
    text = data.get('text', 'Hello world')

    if not video_url:
        return jsonify({"error": "video_url is required"}), 400

    # הורדת וידאו
    input_path = "input.mp4"
    os.system(f"curl -L '{video_url}' -o {input_path}")

    # תרגום
    translated_text = GoogleTranslator(source='auto', target='he').translate(text)
    reshaped_text = arabic_reshaper.reshape(translated_text)
    bidi_text = get_display(reshaped_text)

    # יצירת כתוביות
    clip = VideoFileClip(input_path)
    txt_clip = TextClip(bidi_text, fontsize=40, color='white', bg_color='black', font='Arial')
    txt_clip = txt_clip.set_duration(clip.duration).set_position(('center', 'bottom'))

    final = CompositeVideoClip([clip, txt_clip])
    output_path = "output.mp4"
    final.write_videofile(output_path, codec="libx264", audio_codec="aac")

    return jsonify({"message": "Video processed successfully", "output_path": output_path})

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=10000)
