import os
import json
import requests
import urllib.parse
from io import BytesIO
from pathlib import Path
from flask import Flask, render_template
from flask_socketio import SocketIO
from openai import OpenAI
from dotenv import load_dotenv
from PIL import Image, ImageEnhance, ImageOps, ImageFilter

# ---------------------------------------------------------
# AUTO-RESOLVE PROJECT DIRECTORY
# ---------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.environ.get("GROQ_API_KEY")
)

HISTORY_FILE = BASE_DIR / "chat_history.txt"
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------
# 1. FILE-BASED CONVERSATION BUFFER
# ---------------------------------------------------------
def clear_history_file():
    with open(HISTORY_FILE, "w") as f:
        f.write("")

def append_to_history(sender, msg):
    with open(HISTORY_FILE, "a") as f:
        f.write(f"{sender}: {msg}\n")

def get_recent_history(limit=6):
    if not HISTORY_FILE.exists():
        return []
    with open(HISTORY_FILE, "r") as f:
        lines = [line.strip() for line in f.readlines() if line.strip()]
    return lines[-limit:]

system_state = {
    "current_prompt": "A neutral, faintly lit room with warm ambient light, detailed photography",
    "image_counter": 0,
    "current_image_path": None,
    "screen_width": 1920,
    "screen_height": 1080
}

# ---------------------------------------------------------
# 2. DYNAMIC & SHARPENED IMAGE GENERATION (Pollinations.ai)
# ---------------------------------------------------------
def generate_background_free(visual_prompt, save_path, width=1920, height=1080):
    # Clamp bounds between 512p and 2560p to preserve API reliability while matching target aspect ratio
    target_w = int(max(512, min(width, 2560)))
    target_h = int(max(512, min(height, 1440)))

    print(f"Requesting free image generation [{target_w}x{target_h}] for: {visual_prompt}")
    
    encoded_prompt = urllib.parse.quote(visual_prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={target_w}&height={target_h}&nologo=true"
    
    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            # Read image directly into Pillow
            img = Image.open(BytesIO(response.content)).convert('RGB')
            
            # Apply Unsharp Mask to sharpen details and eliminate scale-up blur
            img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=140, threshold=3))
            
            img.save(save_path, quality=95)
            print(f"Saved sharpened background ({target_w}x{target_h}) to {save_path}")
            return save_path
        else:
            print(f"Image generation failed with status code: {response.status_code}")
            return None
    except Exception as e:
        print(f"Error during image generation: {e}")
        return None

# ---------------------------------------------------------
# 3. LOCAL IMAGE EDITING FOR MOOD (Pillow)
# ---------------------------------------------------------
def apply_mood_shift(input_path, output_path, mood):
    print(f"Applying subtle mood shift: {mood} to {input_path}")
    if not os.path.exists(input_path):
        return None
        
    img = Image.open(input_path).convert('RGB')
    
    enhancer_color = ImageEnhance.Color(img)
    enhancer_brightness = ImageEnhance.Brightness(img)
    enhancer_contrast = ImageEnhance.Contrast(img)
    
    if mood == "warm_happy":
        img = enhancer_brightness.enhance(1.1)
        img = ImageEnhance.Color(img).enhance(1.2)
        overlay = Image.new('RGB', img.size, (255, 200, 0))
        img = Image.blend(img, overlay, 0.08)
    elif mood == "cool_sad":
        img = enhancer_color.enhance(0.6)
        img = enhancer_brightness.enhance(0.85)
        overlay = Image.new('RGB', img.size, (0, 50, 255))
        img = Image.blend(img, overlay, 0.15)
    elif mood == "dark_moody":
        img = enhancer_brightness.enhance(0.6)
        img = enhancer_contrast.enhance(1.2)
        img = enhancer_color.enhance(0.8)
    elif mood == "bright_energetic":
        img = enhancer_brightness.enhance(1.2)
        img = enhancer_color.enhance(1.4)
        img = enhancer_contrast.enhance(1.1)

    # Re-apply subtle sharpening after color processing
    img = img.filter(ImageFilter.UnsharpMask(radius=1, percent=100, threshold=2))
        
    img.save(output_path, quality=95)
    return output_path

# ---------------------------------------------------------
# 4. LLM CONTEXT ANALYZER (Groq / GPT-OSS)
# ---------------------------------------------------------
def analyze_context(history, current_scene):
    prompt_text = f"""
    You are an AI managing the background image of a chatroom. 
    Analyze the following conversation history and determine how the background scene should react.
    
    Current Scene Prompt: "{current_scene}"
    Conversation History:
    {json.dumps(history, indent=2)}
    
    Rules for output:
    1. "change_type": Must be "NONE", "SUBTLE", or "OVERHAUL". 
       - "OVERHAUL": USE THIS FREQUENTLY whenever the TOPIC, subject matter, or context of the conversation changes. (e.g., shifting from casual greetings to talking about space, or shifting from food to music). You do NOT need a physical location change to trigger this; any new topic should trigger a full prompt change.
       - "SUBTLE": USE THIS ONLY if the conversational TOPIC REMAINS EXACTLY THE SAME, but the emotional tone or sentiment shifts (e.g., discussing a video game calmly, then getting frustrated or excited about it).
       - "NONE": Both the topic and the general emotional mood are stable.

    2. "visual_prompt": A highly detailed, cinematic description of what the scene should look like to perfectly encapsulate the topic. (Required if OVERHAUL).
    3. "mood": If "SUBTLE", provide one of these exact strings: "warm_happy", "cool_sad", "dark_moody", or "bright_energetic". If not SUBTLE, output "none".
    
    Return ONLY valid JSON with keys "change_type", "visual_prompt", and "mood".
    """
    
    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt_text}]
    )
    return json.loads(response.choices[0].message.content)

# ---------------------------------------------------------
# 5. FLASK ROUTES & SOCKETS
# ---------------------------------------------------------
@app.route('/')
def index():
    # Pass initial background and prompt to the template on first page load
    initial_bg_url = f"/{system_state['current_image_path']}" if system_state["current_image_path"] else ""
    return render_template(
        'index.html', 
        initial_bg=initial_bg_url, 
        initial_prompt=system_state["current_prompt"]
    )

@socketio.on('send_message')
def handle_message(data):
    sender = data['sender']
    msg_text = data['msg']
    
    # Store dynamic display dimensions from client payload if provided
    client_width = data.get('width', system_state["screen_width"])
    client_height = data.get('height', system_state["screen_height"])
    system_state["screen_width"] = client_width
    system_state["screen_height"] = client_height

    append_to_history(sender, msg_text)
    recent_history = get_recent_history(limit=6)

    socketio.emit('receive_message', {'sender': sender, 'msg': msg_text})

    analysis = analyze_context(recent_history, system_state["current_prompt"])
    print(f"LLM Analysis Decision: {analysis['change_type']}")

    if analysis["change_type"] in ["SUBTLE", "OVERHAUL"]:
        system_state["image_counter"] += 1
        new_image_file = f"static/bg_{system_state['image_counter']}.jpg"
        absolute_new_image_path = BASE_DIR / new_image_file
        
        saved_path = None
        
        if analysis["change_type"] == "OVERHAUL":
            saved_path = generate_background_free(
                visual_prompt=analysis["visual_prompt"], 
                save_path=absolute_new_image_path,
                width=client_width,
                height=client_height
            )
            if saved_path:
                system_state["current_prompt"] = analysis["visual_prompt"]
                
        elif analysis["change_type"] == "SUBTLE":
            absolute_current_image_path = BASE_DIR / system_state["current_image_path"]
            mood = analysis.get("mood", "warm_happy")
            
            saved_path = apply_mood_shift(
                input_path=absolute_current_image_path, 
                output_path=absolute_new_image_path, 
                mood=mood
            )

        if saved_path:
            system_state["current_image_path"] = new_image_file
            
            socketio.emit('update_background', {
                'url': f"/{new_image_file}",
                'prompt': analysis["visual_prompt"] if analysis["change_type"] == "OVERHAUL" else f"Mood shifted to {analysis.get('mood')}"
            })

if __name__ == '__main__':
    print("Clearing old chat history...")
    clear_history_file()
    
    print("Generating initial background...")
    system_state["current_image_path"] = "static/bg_0.jpg"
    generate_background_free(
        system_state["current_prompt"], 
        BASE_DIR / system_state["current_image_path"],
        width=system_state["screen_width"],
        height=system_state["screen_height"]
    )
    
    socketio.run(app, debug=True, port=5555, allow_unsafe_werkzeug=True)