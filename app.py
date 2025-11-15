import os
import json
import sqlite3
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, session, make_response
from flask_cors import CORS
from werkzeug.utils import secure_filename
import google.generativeai as genai
from PIL import Image
import io

app = Flask(__name__)

# CRITICAL FIX: Proper CORS configuration for Azure Static Web Apps
CORS(app, 
     resources={r"/api/*": {
         "origins": ["https://aifashionfitstorage.z30.web.core.windows.net", "*"],
         "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
         "allow_headers": ["Content-Type", "Authorization"],
         "supports_credentials": True,
         "expose_headers": ["Content-Type"]
     }})

# Session configuration for cross-origin requests
app.secret_key = os.environ.get('SESSION_SECRET', 'dev-secret-key-change-in-production-12345')
app.config['SESSION_COOKIE_SAMESITE'] = 'None'
app.config['SESSION_COOKIE_SECURE'] = True  # Required for HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True

UPLOAD_FOLDER = 'static/uploads'
GENERATED_FOLDER = 'static/generated'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['GENERATED_FOLDER'] = GENERATED_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(GENERATED_FOLDER, exist_ok=True)

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
UPI_ID = os.environ.get('UPI_ID', 'your-upi@bank')
UPI_NAME = os.environ.get('UPI_NAME', 'Your Name')

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


# Add CORS headers to all responses
@app.after_request
def after_request(response):
    origin = request.headers.get('Origin')
    if origin:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response


def init_db():
    """Initialize database"""
    print("🔄 Initializing database...")
    conn = sqlite3.connect('fashion_fit.db')
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS user_info (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        age INTEGER,
        gender TEXT,
        skin_tone TEXT,
        body_shape TEXT,
        image_path TEXT,
        face_shape TEXT,
        hair_texture TEXT,
        hairstyle_suggestions TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_id TEXT UNIQUE,
        user_id INTEGER,
        amount REAL,
        purpose TEXT,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        confirmed_at TIMESTAMP
    )''')
    
    conn.commit()
    
    c.execute("PRAGMA table_info(user_info)")
    existing_columns = [col[1] for col in c.fetchall()]
    
    if 'face_shape' not in existing_columns:
        try:
            c.execute("ALTER TABLE user_info ADD COLUMN face_shape TEXT DEFAULT 'Oval'")
            print("✅ Added face_shape column")
        except: pass
    
    if 'hair_texture' not in existing_columns:
        try:
            c.execute("ALTER TABLE user_info ADD COLUMN hair_texture TEXT DEFAULT 'Straight'")
            print("✅ Added hair_texture column")
        except: pass
    
    if 'hairstyle_suggestions' not in existing_columns:
        try:
            c.execute("ALTER TABLE user_info ADD COLUMN hairstyle_suggestions TEXT")
            print("✅ Added hairstyle_suggestions column")
        except: pass
    
    conn.commit()
    conn.close()
    print("✨ Database ready!\n")


init_db()


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def analyze_user_photo(img_path):
    """Photo analysis with AI"""
    if not GEMINI_API_KEY:
        return {
            "skin_tone": "Medium",
            "body_shape": "Average",
            "face_shape": "Oval",
            "hair_texture": "Straight",
            "current_hair_length": "Medium",
            "hair_color": "Black"
        }

    try:
        model = genai.GenerativeModel("gemini-2.0-flash-exp")
        with open(img_path, "rb") as f:
            img_data = f.read()
        img = Image.open(io.BytesIO(img_data))

        prompt = """Analyze this person's appearance and return ONLY a JSON object:
{
    "skin_tone": "Fair/Wheatish/Dark",
    "body_shape": "Slim/Average/Curvy",
    "face_shape": "Oval/Round/Square/Heart/Diamond/Oblong",
    "hair_texture": "Straight/Wavy/Curly/Coily",
    "current_hair_length": "Short/Medium/Long",
    "hair_color": "Black/Brown/Blonde/Red/Gray/Other"
}"""

        response = model.generate_content([prompt, img])
        response_text = response.text.strip()
        response_text = response_text.replace('```json', '').replace('```', '').strip()
        return json.loads(response_text)
    except Exception as e:
        print(f"Error analyzing photo: {e}")
        return {
            "skin_tone": "Medium",
            "body_shape": "Average",
            "face_shape": "Oval",
            "hair_texture": "Straight",
            "current_hair_length": "Medium",
            "hair_color": "Black"
        }


def generate_hairstyle_suggestions(user_analysis, user_gender, user_age):
    """Generate hairstyle suggestions"""
    if not GEMINI_API_KEY:
        return {"suggestions": [{
            "name": "Classic Layered Cut",
            "description": "A versatile style that suits most face shapes",
            "best_for": "Everyday wear",
            "maintenance": "Low",
            "styling_time": "10-15 minutes",
            "products_needed": ["Styling cream"],
            "styling_tips": "Blow dry with a round brush"
        }]}

    try:
        model = genai.GenerativeModel("gemini-2.0-flash-exp")
        prompt = f"""Professional hairstylist suggestions for:
- Gender: {user_gender}, Age: {user_age}
- Face: {user_analysis.get('face_shape', 'Oval')}
- Hair: {user_analysis.get('hair_texture', 'Straight')}

Return ONLY JSON array with 5 hairstyles:
[{{"name": "...", "description": "...", "best_for": "...", "maintenance": "Low/Medium/High", "styling_time": "...", "products_needed": ["..."], "styling_tips": "..."}}]"""

        response = model.generate_content(prompt)
        response_text = response.text.strip().replace('```json', '').replace('```', '').strip()
        return {"suggestions": json.loads(response_text)}
    except Exception as e:
        print(f"Error generating hairstyles: {e}")
        return {"suggestions": []}


def match_outfits(user):
    """Match outfits from JSON"""
    try:
        with open("outfits.json") as f:
            outfits = json.load(f)
    except:
        return []

    matched = []
    for outfit in outfits:
        age_group = outfit.get("age_group", "18-100")
        min_age, max_age = map(int, age_group.split("-")) if "-" in age_group else (18, 100)
        
        gender_match = user["gender"].lower() == outfit.get("gender", "").lower() or outfit.get("gender", "").lower() == "unisex"
        age_match = min_age <= user["age"] <= max_age
        skin_match = user["skin_tone"] in outfit.get("skin_tones", [])
        body_match = user["body_shape"] in outfit.get("body_shapes", [])

        if gender_match and age_match and skin_match and body_match:
            matched.append(outfit)

    return matched[:5]


def explain_match(user, outfit):
    """Generate explanation"""
    if not GEMINI_API_KEY:
        return f"This {outfit['name']} complements your style!"
    try:
        model = genai.GenerativeModel("gemini-2.0-flash-exp")
        prompt = f"{user['age']}y/o {user['gender']}, {user['skin_tone']} skin, {user['body_shape']} shape. Why '{outfit['name']}' suits them? (20 words max)"
        response = model.generate_content(prompt)
        return response.text.strip()
    except:
        return f"This {outfit['name']} complements your style!"


# API Routes
@app.route('/api/health', methods=['GET', 'OPTIONS'])
def health():
    """Health check"""
    return jsonify({"status": "ok", "message": "Backend running"}), 200


@app.route('/api/analyze', methods=['POST', 'OPTIONS'])
def analyze():
    """Analyze user profile"""
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        name = request.form.get('name')
        age = int(request.form.get('age', 0))
        gender = request.form.get('gender')
        skin_tone = request.form.get('skin_tone')
        body_shape = request.form.get('body_shape')

        print(f"📝 Analysis request: {name}, {age}, {gender}")

        if not all([name, age, gender, skin_tone, body_shape]):
            return jsonify({"error": "Missing required fields"}), 400

        if 'photo' not in request.files:
            return jsonify({"error": "No photo uploaded"}), 400

        file = request.files['photo']
        if not file.filename or not allowed_file(file.filename):
            return jsonify({"error": "Invalid file type"}), 400

        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(filepath)

        print(f"📸 Photo saved: {filepath}")

        # AI analysis
        ai_analysis = analyze_user_photo(filepath)
        hairstyle_data = generate_hairstyle_suggestions(ai_analysis, gender, age)

        # Save to database
        conn = sqlite3.connect('fashion_fit.db')
        c = conn.cursor()
        c.execute(
            '''INSERT INTO user_info (name, age, gender, skin_tone, body_shape, image_path, face_shape, hair_texture, hairstyle_suggestions)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (name, age, gender, skin_tone, body_shape, filepath,
             ai_analysis.get('face_shape', 'Oval'),
             ai_analysis.get('hair_texture', 'Straight'),
             json.dumps(hairstyle_data)))
        user_id = c.lastrowid
        conn.commit()
        conn.close()

        print(f"✅ User saved: ID {user_id}")

        # Store in session
        session['user_id'] = user_id
        session['user_name'] = name
        session['user_age'] = age
        session['user_gender'] = gender
        session['user_skin_tone'] = skin_tone
        session['user_body_shape'] = body_shape
        session['user_image'] = filepath
        session['face_shape'] = ai_analysis.get('face_shape', 'Oval')
        session['hair_texture'] = ai_analysis.get('hair_texture', 'Straight')
        session['hairstyle_suggestions'] = json.dumps(hairstyle_data)

        response = make_response(jsonify({
            "success": True,
            "user_id": user_id,
            "analysis": ai_analysis,
            "hairstyles": hairstyle_data
        }))
        
        return response, 200

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/recommendations', methods=['GET', 'OPTIONS'])
def get_recommendations():
    """Get recommendations"""
    if request.method == 'OPTIONS':
        return '', 204
        
    print(f"🔍 Session data: {dict(session)}")
    
    if 'user_id' not in session:
        return jsonify({"error": "User not found. Please complete profile analysis first."}), 401

    user = {
        'name': session.get('user_name'),
        'age': session.get('user_age'),
        'gender': session.get('user_gender'),
        'skin_tone': session.get('user_skin_tone'),
        'body_shape': session.get('user_body_shape'),
        'image_path': session.get('user_image'),
        'face_shape': session.get('face_shape', 'Oval'),
        'hair_texture': session.get('hair_texture', 'Straight')
    }

    hairstyle_json = session.get('hairstyle_suggestions', '{"suggestions": []}')
    hairstyle_data = json.loads(hairstyle_json)

    matched_outfits = match_outfits(user)
    outfits_with_explanations = []
    for outfit in matched_outfits:
        outfit_copy = outfit.copy()
        outfit_copy['explanation'] = explain_match(user, outfit)
        outfits_with_explanations.append(outfit_copy)

    return jsonify({
        "user": user,
        "outfits": outfits_with_explanations,
        "hairstyles": hairstyle_data['suggestions']
    }), 200


@app.route('/api/payment/initiate', methods=['POST', 'OPTIONS'])
def initiate_payment():
    """Initiate payment"""
    if request.method == 'OPTIONS':
        return '', 204
        
    data = request.get_json()
    amount = data.get('amount', '10.00')
    purpose = data.get('purpose', 'Coffee')
    
    if 'user_id' not in session:
        return jsonify({"error": "User not found"}), 401

    transaction_id = f"TXN{uuid.uuid4().hex[:12].upper()}"
    
    conn = sqlite3.connect('fashion_fit.db')
    c = conn.cursor()
    c.execute(
        '''INSERT INTO payments (transaction_id, user_id, amount, purpose, status)
           VALUES (?, ?, ?, ?, 'pending')''',
        (transaction_id, session['user_id'], float(amount), purpose))
    conn.commit()
    conn.close()

    upi_url = f"upi://pay?pa={UPI_ID}&pn={UPI_NAME}&am={amount}&cu=INR&tn={transaction_id}-{purpose}"
    
    return jsonify({
        "transaction_id": transaction_id,
        "amount": amount,
        "upi_url": upi_url,
        "upi_id": UPI_ID,
        "upi_name": UPI_NAME
    }), 200


@app.route('/api/payment/confirm', methods=['POST', 'OPTIONS'])
def confirm_payment():
    """Confirm payment"""
    if request.method == 'OPTIONS':
        return '', 204
        
    data = request.get_json()
    transaction_id = data.get('transaction_id')
    paid = data.get('paid', False)
    
    conn = sqlite3.connect('fashion_fit.db')
    c = conn.cursor()
    status = 'completed' if paid else 'failed'
    c.execute(
        '''UPDATE payments SET status = ?, confirmed_at = ? WHERE transaction_id = ?''',
        (status, datetime.now(), transaction_id))
    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "status": status,
        "transaction_id": transaction_id
    }), 200


@app.route('/api/config', methods=['GET', 'OPTIONS'])
def get_config():
    """Get config"""
    if request.method == 'OPTIONS':
        return '', 204
    return jsonify({
        "upi_id": UPI_ID,
        "upi_name": UPI_NAME,
        "has_gemini": bool(GEMINI_API_KEY)
    }), 200


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)