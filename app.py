from flask import Flask, render_template
from flask_socketio import SocketIO

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins="*")

THEME_MAP = {
    "space": {"galaxy", "stars", "moon", "nasa", "orbit", "space"},
    "nature": {"tree", "forest", "hiking", "leaves", "grass", "nature"},
    "ocean": {"beach", "surf", "waves", "fish", "sand", "ocean", "beach"},
    "code": {"python", "javascript", "html", "css", "programming", "code"}
}
THEMES = {
    "space": "https://images.unsplash.com/photo-1451187580459-43490279c0fa?q=80&w=2072&auto=format&fit=crop",
    "nature": "https://images.unsplash.com/photo-1441974231531-c6227db76b6e?q=80&w=2071&auto=format&fit=crop",
    "ocean": "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?q=80&w=2073&auto=format&fit=crop",
    "code": "https://images.unsplash.com/photo-1515879218367-8466d910aaa4?q=80&w=2069&auto=format&fit=crop"
}

def analyze_subject(message):
    words = set(message.lower().split())
    for theme, keywords in THEME_MAP.items():
        if not words.isdisjoint(keywords):
            return theme
    return None

@app.route('/')
def index():
    return render_template('front.html')

@socketio.on('send_message')
def handle_message(data):
    msg_text = data['msg']
    theme_key = analyze_subject(msg_text)
    image_url = THEMES.get(theme_key) if theme_key else None
    print(f"Received: {msg_text} | Theme: {theme_key}")
    socketio.emit('receive_message', {'msg': msg_text, 'url': image_url})

if __name__ == '__main__':
    socketio.run(app, debug=False, port=5555, allow_unsafe_werkzeug=True)


# online
import os

if __name__ == '__main__':
    # Use the port assigned by the host, or default to 5555
    port = int(os.environ.get("PORT", 5555))
    socketio.run(app, host='0.0.0.0', port=port)