import os
import json
import sqlite3
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, session
from flask_cors import CORS
from werkzeug.utils import secure_filename
import google.generativeai as genai
from PIL import Image
import io

app = Flask(__name__)
CORS(app, 
     supports_credentials=True,
     origins=['https://aifashionfitstorage.z30.web.core.windows.net/'],  # In production, replace with your frontend domain
     allow_headers=['Content-Type', 'Authorization'],
     methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])

app.secret_key = os.environ.get('SESSION_SECRET', 'dev-secret-key-change-in-production')

UPLOAD_FOLDER = 'static/uploads'
GENERATED_FOLDER = 'static/generated'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['GENERATED_FOLDER'] = GENERATED_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Create folders if they don't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(GENERATED_FOLDER, exist_ok=True)

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
UPI_ID = os.environ.get('UPI_ID', 'your-upi@bank')
UPI_NAME = os.environ.get('UPI_NAME', 'Your Name')

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


def init_db():
    """Initialize database with all tables and run migrations"""
    print("🔄 Initializing database...")
    conn = sqlite3.connect('fashion_fit.db')
    c = conn.cursor()
    
    # Create user_info table
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
    
    # Create payments table
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
    
    # Run migrations for existing databases
    print("🔄 Running migrations...")
    
    # Get existing columns
    c.execute("PRAGMA table_info(user_info)")
    existing_columns = [col[1] for col in c.fetchall()]
    
    # Add face_shape if missing
    if 'face_shape' not in existing_columns:
        try:
            c.execute("ALTER TABLE user_info ADD COLUMN face_shape TEXT DEFAULT 'Oval'")
            print("✅ Added face_shape column")
        except sqlite3.OperationalError as e:
            print(f"⚠️  face_shape migration error: {e}")
    
    # Add hair_texture if missing
    if 'hair_texture' not in existing_columns:
        try:
            c.execute("ALTER TABLE user_info ADD COLUMN hair_texture TEXT DEFAULT 'Straight'")
            print("✅ Added hair_texture column")
        except sqlite3.OperationalError as e:
            print(f"⚠️  hair_texture migration error: {e}")
    
    # Add hairstyle_suggestions if missing
    if 'hairstyle_suggestions' not in existing_columns:
        try:
            c.execute("ALTER TABLE user_info ADD COLUMN hairstyle_suggestions TEXT")
            print("✅ Added hairstyle_suggestions column")
        except sqlite3.OperationalError as e:
            print(f"⚠️  hairstyle_suggestions migration error: {e}")
    
    # Add created_at if missing
    if 'created_at' not in existing_columns:
        try:
            c.execute("ALTER TABLE user_info ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
            print("✅ Added created_at column")
        except sqlite3.OperationalError as e:
            print(f"⚠️  created_at migration error: {e}")
    
    conn.commit()
    
    # Verify final structure
    c.execute("PRAGMA table_info(user_info)")
    columns = c.fetchall()
    print("\n📊 Final user_info table structure:")
    for col in columns:
        print(f"   - {col[1]} ({col[2]})")
    
    c.execute("PRAGMA table_info(payments)")
    columns = c.fetchall()
    print("\n💳 Final payments table structure:")
    for col in columns:
        print(f"   - {col[1]} ({col[2]})")
    
    conn.close()
    print("✨ Database initialization complete!\n")


init_db()


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def analyze_user_photo(img_path):
    """Enhanced photo analysis including face shape and hair texture"""
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

        prompt = """Analyze this person's appearance comprehensively and return ONLY a JSON object with this exact format:
{
    "skin_tone": "Fair/Wheatish/Dark",
    "body_shape": "Slim/Average/Curvy",
    "face_shape": "Oval/Round/Square/Heart/Diamond/Oblong",
    "hair_texture": "Straight/Wavy/Curly/Coily",
    "current_hair_length": "Short/Medium/Long",
    "hair_color": "Black/Brown/Blonde/Red/Gray/Other"
}

Be specific and accurate in your assessment."""

        response = model.generate_content([prompt, img])
        response_text = response.text.strip()

        # Clean up response
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.startswith('```'):
            response_text = response_text[3:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        response_text = response_text.strip()

        result = json.loads(response_text)
        return result
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
    """Generate personalized hairstyle suggestions using Gemini AI"""
    if not GEMINI_API_KEY:
        return {
            "suggestions": [{
                "name": "Classic Layered Cut",
                "description": "A versatile style that suits most face shapes",
                "best_for": "Everyday wear",
                "maintenance": "Low",
                "styling_time": "10-15 minutes",
                "products_needed": ["Styling cream"],
                "styling_tips": "Blow dry with a round brush"
            }]
        }

    try:
        model = genai.GenerativeModel("gemini-2.0-flash-exp")
        prompt = f"""You are a professional hairstylist AI. Based on the following client profile, suggest 5 specific hairstyles:

Client Profile:
- Gender: {user_gender}
- Age: {user_age}
- Face Shape: {user_analysis.get('face_shape', 'Oval')}
- Hair Texture: {user_analysis.get('hair_texture', 'Straight')}
- Current Hair Length: {user_analysis.get('current_hair_length', 'Medium')}
- Hair Color: {user_analysis.get('hair_color', 'Black')}
- Skin Tone: {user_analysis.get('skin_tone', 'Medium')}

Provide ONLY a JSON array with 5 hairstyle suggestions in this exact format:
[
    {{
        "name": "Hairstyle Name",
        "description": "Why this suits their face shape and features (2-3 sentences)",
        "best_for": "What occasions/lifestyle this works for",
        "maintenance": "Low/Medium/High",
        "styling_time": "5-10 minutes/10-20 minutes/20+ minutes",
        "products_needed": ["Product 1", "Product 2"],
        "styling_tips": "Quick tip on how to style it"
    }}
]

Make suggestions practical, modern, and specifically tailored to their face shape and hair texture."""

        response = model.generate_content(prompt)
        response_text = response.text.strip()

        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.startswith('```'):
            response_text = response_text[3:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        response_text = response_text.strip()

        suggestions = json.loads(response_text)
        return {"suggestions": suggestions}

    except Exception as e:
        print(f"Error generating hairstyle suggestions: {e}")
        return {"suggestions": []}


def match_outfits(user):
    """Match outfits based on user's profile"""
    try:
        with open("outfits.json") as f:
            outfits = json.load(f)
    except FileNotFoundError:
        return []

    matched = []
    user_age = user["age"]
    user_gender = user["gender"].lower()
    user_skin_tone = user["skin_tone"]
    user_body_shape = user["body_shape"]

    for outfit in outfits:
        age_group = outfit.get("age_group", "18-100")
        age_parts = age_group.split("-")
        min_age = int(age_parts[0])
        max_age = int(age_parts[1]) if len(age_parts) > 1 else 100

        outfit_gender = outfit.get("gender", "").lower()
        gender_match = (user_gender == outfit_gender or outfit_gender == "unisex")
        age_match = min_age <= user_age <= max_age
        skin_match = user_skin_tone in outfit.get("skin_tones", [])
        body_match = user_body_shape in outfit.get("body_shapes", [])

        if gender_match and age_match and skin_match and body_match:
            matched.append(outfit)

    return matched[:5] if len(matched) >= 5 else matched


def explain_match(user, outfit):
    """Generate AI explanation for outfit match"""
    if not GEMINI_API_KEY:
        return f"This {outfit['name']} is a great match for your style!"
    try:
        model = genai.GenerativeModel("gemini-2.0-flash-exp")
        prompt = f"""The user is a {user['age']} year old {user['gender']} with {user['skin_tone']} skin tone and {user['body_shape']} body shape.
Explain in ONE friendly sentence (max 20 words) why '{outfit['name']}' suits them perfectly."""
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"This {outfit['name']} complements your style perfectly!"


# API Routes
@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({"status": "ok", "message": "Backend is running"})



@app.route('/api/analyze', methods=['POST'])
def analyze():
    """Analyze user profile and photo"""
    try:
        name = request.form.get('name')
        age = int(request.form.get('age', 0))
        gender = request.form.get('gender')
        skin_tone = request.form.get('skin_tone')
        body_shape = request.form.get('body_shape')

        if not all([name, age, gender, skin_tone, body_shape]):
            return jsonify({"error": "Missing required fields"}), 400

        if 'photo' not in request.files:
            return jsonify({"error": "No photo uploaded"}), 400

        file = request.files['photo']
        if not file.filename or not allowed_file(file.filename):
            return jsonify({"error": "Invalid file"}), 400

        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(filepath)

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

        return jsonify({
            "success": True,
            "user_id": user_id,
            "analysis": ai_analysis,
            "hairstyles": hairstyle_data
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/recommendations', methods=['GET'])
def get_recommendations():
    """Get outfit and hairstyle recommendations"""
    if 'user_id' not in session:
        return jsonify({"error": "User not found"}), 401

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
        explanation = explain_match(user, outfit)
        outfit_copy = outfit.copy()
        outfit_copy['explanation'] = explanation
        outfits_with_explanations.append(outfit_copy)

    return jsonify({
        "user": user,
        "outfits": outfits_with_explanations,
        "hairstyles": hairstyle_data['suggestions']
    })


@app.route('/api/payment/initiate', methods=['POST'])
def initiate_payment():
    """Initiate payment"""
    data = request.get_json()
    amount = data.get('amount', '10.00')
    purpose = data.get('purpose', 'VirtualTryOn')
    
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
    })


@app.route('/api/payment/confirm', methods=['POST'])
def confirm_payment():
    """Confirm payment status"""
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
    })


@app.route('/api/config', methods=['GET'])
def get_config():
    """Get app configuration for frontend"""
    return jsonify({
        "upi_id": UPI_ID,
        "upi_name": UPI_NAME,
        "has_gemini": bool(GEMINI_API_KEY)
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)