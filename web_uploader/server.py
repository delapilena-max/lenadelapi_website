from flask import Flask, request, send_from_directory
import subprocess
import os

app = Flask(__name__, static_folder='.')

@app.route('/')
def home():
    return send_from_directory('.', 'index.html')

@app.route('/oauth/start')
def oauth_start():
    return "Show TikTok OAuth here (sandbox)."

@app.route('/upload', methods=['POST'])
def upload():
    file = request.files['video']
    path = 'demo_video.mp4'
    file.save(path)

    subprocess.run(['python', '../upload_tiktok_personas.py'])
    return 'OK'

if __name__ == '__main__':
    app.run(port=5000)
