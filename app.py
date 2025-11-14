import os
import json
import pyodbc
import uuid
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from werkzeug.utils import secure_filename
from urllib.parse import unquote
import google.generativeai as genai
from PIL import Image
import io
import requests

app = Flask(__name__)
app.secret_key = os.environ.get('SESSION_SECRET',
                                'dev-secret-key-change-in-production')

UPLOAD_FOLDER = 'static/uploads'
GENERATED_FOLDER = 'static/generated'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['GENERATED_FOLDER'] = GENERATED_FOLDER

# Azure SQL Database Configuration
AZURE_SQL_SERVER = os.environ.get('AZURE_SQL_SERVER', '')  # e.g., 'yourserver.database.windows.net'
AZURE_SQL_DATABASE = os.environ.get('AZURE_SQL_DATABASE', '')  # e.g., 'fashion_fit_db'
AZURE_SQL_USERNAME = os.environ.get('AZURE_SQL_USERNAME', '')
AZURE_SQL_PASSWORD = os.environ.get('AZURE_SQL_PASSWORD', '')

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
UPI_ID = os.environ.get('UPI_ID', 'your-upi@bank')
UPI_NAME = os.environ.get('UPI_NAME', 'Your Name')

# 👇 Frontend (Blob static website) base URL
FRONTEND_URL = os.environ.get(
    'FRONTEND_URL',
    'https://aifashionfitstorage.z30.web.core.windows.net'
)

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


def get_db_connection():
    """Create and return Azure SQL Database connection"""
    try:
        connection_string = (
            f'DRIVER={{ODBC Driver 18 for SQL Server}};'
            f'SERVER={AZURE_SQL_SERVER};'
            f'DATABASE={AZURE_SQL_DATABASE};'
            f'UID={AZURE_SQL_USERNAME};'
            f'PWD={AZURE_SQL_PASSWORD};'
            f'Encrypt=yes;'
            f'TrustServerCertificate=no;'
            f'Connection Timeout=30;'
        )
        conn = pyodbc.connect(connection_string)
        return conn
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        raise


def init_db():
    """Initialize database with all tables and migrations"""
    print("🔄 Initializing Azure SQL Database...")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Create user_info table with all columns
        print("📊 Creating/updating user_info table...")
        cursor.execute('''
            IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'user_info')
            BEGIN
                CREATE TABLE user_info (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    name NVARCHAR(255),
                    age INT,
                    gender NVARCHAR(50),
                    skin_tone NVARCHAR(100),
                    body_shape NVARCHAR(100),
                    image_path NVARCHAR(500),
                    face_shape NVARCHAR(100) DEFAULT 'Oval',
                    hair_texture NVARCHAR(100) DEFAULT 'Straight',
                    hairstyle_suggestions NVARCHAR(MAX),
                    created_at DATETIME2 DEFAULT GETDATE(),
                    updated_at DATETIME2 DEFAULT GETDATE()
                )
            END
        ''')
        print("✅ user_info table ready")
        
        # Migration: Add missing columns if table already exists
        print("🔄 Running migrations for user_info...")
        
        # Check and add face_shape column
        cursor.execute('''
            IF NOT EXISTS (
                SELECT * FROM sys.columns 
                WHERE object_id = OBJECT_ID('user_info') 
                AND name = 'face_shape'
            )
            BEGIN
                ALTER TABLE user_info ADD face_shape NVARCHAR(100) DEFAULT 'Oval'
            END
        ''')
        
        # Check and add hair_texture column
        cursor.execute('''
            IF NOT EXISTS (
                SELECT * FROM sys.columns 
                WHERE object_id = OBJECT_ID('user_info') 
                AND name = 'hair_texture'
            )
            BEGIN
                ALTER TABLE user_info ADD hair_texture NVARCHAR(100) DEFAULT 'Straight'
            END
        ''')
        
        # Check and add hairstyle_suggestions column
        cursor.execute('''
            IF NOT EXISTS (
                SELECT * FROM sys.columns 
                WHERE object_id = OBJECT_ID('user_info') 
                AND name = 'hairstyle_suggestions'
            )
            BEGIN
                ALTER TABLE user_info ADD hairstyle_suggestions NVARCHAR(MAX)
            END
        ''')
        
        # Check and add created_at column
        cursor.execute('''
            IF NOT EXISTS (
                SELECT * FROM sys.columns 
                WHERE object_id = OBJECT_ID('user_info') 
                AND name = 'created_at'
            )
            BEGIN
                ALTER TABLE user_info ADD created_at DATETIME2 DEFAULT GETDATE()
            END
        ''')
        
        # Check and add updated_at column
        cursor.execute('''
            IF NOT EXISTS (
                SELECT * FROM sys.columns 
                WHERE object_id = OBJECT_ID('user_info') 
                AND name = 'updated_at'
            )
            BEGIN
                ALTER TABLE user_info ADD updated_at DATETIME2 DEFAULT GETDATE()
            END
        ''')
        
        print("✅ user_info migrations complete")
        
        # Create payments table
        print("📊 Creating/updating payments table...")
        cursor.execute('''
            IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'payments')
            BEGIN
                CREATE TABLE payments (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    transaction_id NVARCHAR(100) UNIQUE NOT NULL,
                    user_id INT,
                    amount DECIMAL(10, 2),
                    purpose NVARCHAR(255),
                    status NVARCHAR(50) DEFAULT 'pending',
                    created_at DATETIME2 DEFAULT GETDATE(),
                    confirmed_at DATETIME2,
                    FOREIGN KEY (user_id) REFERENCES user_info(id)
                )
            END
        ''')
        print("✅ payments table ready")
        
        # Create indexes for better performance
        print("🔄 Creating indexes...")
        cursor.execute('''
            IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_user_info_gender_age')
            BEGIN
                CREATE INDEX idx_user_info_gender_age ON user_info(gender, age)
            END
        ''')
        
        cursor.execute('''
            IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_payments_transaction_id')
            BEGIN
                CREATE INDEX idx_payments_transaction_id ON payments(transaction_id)
            END
        ''')
        
        cursor.execute('''
            IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_payments_user_id')
            BEGIN
                CREATE INDEX idx_payments_user_id ON payments(user_id)
            END
        ''')
        print("✅ Indexes created")
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print("✨ Database initialization complete!")
        
    except Exception as e:
        print(f"❌ Database initialization error: {e}")
        raise


# Initialize database on startup
try:
    init_db()
except Exception as e:
    print(f"⚠️  Warning: Could not initialize database on startup: {e}")


def allowed_file(filename):
    return '.' in filename and filename.rsplit(
        '.', 1)[1].lower() in ALLOWED_EXTENSIONS


def analyze_user_photo(img_path):
    """Enhanced photo analysis including face shape and hair texture"""
    if not GEMINI_API_KEY:
        return {
            "skin_tone": "Honey",
            "body_shape": "Mesomorph",
            "face_shape": "Oval",
            "hair_texture": "Straight"
        }

    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
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
            "skin_tone": "Honey",
            "body_shape": "Mesomorph",
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
                "maintenance": "Low",
                "styling_time": "10-15 minutes"
            }]
        }

    try:
        model = genai.GenerativeModel("gemini-2.5-flash")

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

        # Clean up response
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
        return {
            "suggestions": [{
                "name": "Personalized Style",
                "description": f"A flattering style for your {user_analysis.get('face_shape', 'unique')} face shape",
                "best_for": "Everyday wear",
                "maintenance": "Medium",
                "styling_time": "10-15 minutes",
                "products_needed": ["Styling cream", "Hair spray"],
                "styling_tips": "Consult with a professional stylist for best results"
            }]

        }


def match_outfits(user):
    """Match outfits based on user's exact skin tone, body shape, age, and gender."""
    try:
        with open("outfits.json") as f:
            outfits = json.load(f)
    except FileNotFoundError:
        print("⚠️ outfits.json not found!")
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
        skin_tones = outfit.get("skin_tones", [])
        skin_match = user_skin_tone in skin_tones
        body_shapes = outfit.get("body_shapes", [])
        body_match = user_body_shape in body_shapes

        if gender_match and age_match and skin_match and body_match:
            matched.append(outfit)

    return matched[:5] if len(matched) >= 5 else matched


def explain_match(user, outfit):
    if not GEMINI_API_KEY:
        return f"This {outfit['name']} is a great match for your style!"
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        prompt = f"""The user is a {user['age']} year old {user['gender']} with {user['skin_tone']} skin tone and {user['body_shape']} body shape.
Explain in ONE friendly sentence (max 20 words) why '{outfit['name']}' suits them perfectly."""
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Error generating explanation: {e}")
        return f"This {outfit['name']} complements your style perfectly!"


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/profile')
def profile():
    # Redirect backend /profile to Blob static profile page
    return redirect(f"{FRONTEND_URL}/profile.html")


@app.route('/analyze', methods=['POST'])
def analyze():
    name = request.form.get('name')
    age_str = request.form.get('age')
    if not age_str:
        return redirect(f"{FRONTEND_URL}/profile.html")
    age = int(age_str)
    gender = request.form.get('gender')
    skin_tone = request.form.get('skin_tone')
    body_shape = request.form.get('body_shape')

    if not all([name, age, gender, skin_tone, body_shape]):
        print("❌ Missing required fields!")
        return redirect(f"{FRONTEND_URL}/profile.html")

    if 'photo' not in request.files:
        return redirect(f"{FRONTEND_URL}/profile.html")

    file = request.files['photo']
    if not file.filename or file.filename == '':
        return redirect(f"{FRONTEND_URL}/profile.html")

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(filepath)

        # Enhanced AI analysis
        ai_analysis = analyze_user_photo(filepath)

        # Generate hairstyle suggestions
        hairstyle_data = generate_hairstyle_suggestions(ai_analysis, gender, age)

        print(f"\n👤 User Profile Created:")
        print(f"   Name: {name}")
        print(f"   Face Shape: {ai_analysis.get('face_shape', 'N/A')}")
        print(f"   Hair Texture: {ai_analysis.get('hair_texture', 'N/A')}")

        # Save to Azure SQL Database
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            '''INSERT INTO user_info (name, age, gender, skin_tone, body_shape, image_path, face_shape, hair_texture, hairstyle_suggestions)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (name, age, gender, skin_tone, body_shape, filepath,
             ai_analysis.get('face_shape', 'Oval'),
             ai_analysis.get('hair_texture', 'Straight'), 
             json.dumps(hairstyle_data)))
        
        # Get the inserted ID
        cursor.execute('SELECT @@IDENTITY AS id')
        user_id = cursor.fetchone()[0]
        
        conn.commit()
        cursor.close()
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

        return redirect(url_for('recommendations'))

    return redirect(f"{FRONTEND_URL}/profile.html")


@app.route('/recommendations')
def recommendations():
    if 'user_id' not in session:
        return redirect(f"{FRONTEND_URL}/profile.html")

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

    # Get hairstyle suggestions
    hairstyle_json = session.get('hairstyle_suggestions', '{"suggestions": []}')
    hairstyle_data = json.loads(hairstyle_json)

    matched_outfits = match_outfits(user)
    outfits_with_explanations = []
    for outfit in matched_outfits:
        explanation = explain_match(user, outfit)
        outfit_copy = outfit.copy()
        outfit_copy['explanation'] = explanation
        outfits_with_explanations.append(outfit_copy)

    return render_template('recommendations.html',
                           user=user,
                           outfits=outfits_with_explanations,
                           hairstyles=hairstyle_data['suggestions'],
                           upi_id=UPI_ID,
                           upi_name=UPI_NAME)


@app.route('/hairstyles')
def hairstyles():
    """Dedicated page for hairstyle suggestions"""
    if 'user_id' not in session:
        return redirect(f"{FRONTEND_URL}/profile.html")

    user = {
        'name': session.get('user_name'),
        'age': session.get('user_age'),
        'gender': session.get('user_gender'),
        'image_path': session.get('user_image'),
        'face_shape': session.get('face_shape', 'Oval'),
        'hair_texture': session.get('hair_texture', 'Straight')
    }

    hairstyle_json = session.get('hairstyle_suggestions', '{"suggestions": []}')
    hairstyle_data = json.loads(hairstyle_json)

    return render_template('hairstyles.html',
                           user=user,
                           hairstyles=hairstyle_data['suggestions'])


@app.route('/confirm_payment', methods=['POST'])
def confirm_payment():
    paid = request.form.get('paid')
    transaction_id = request.form.get('transaction_id')
    outfit_name = request.form.get('outfit_name', 'N/A')

    if paid == "yes":
        # Update payment status in database
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                '''UPDATE payments 
                   SET status = 'confirmed', confirmed_at = GETDATE() 
                   WHERE transaction_id = ?''',
                (transaction_id,))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"Error updating payment status: {e}")
        
        return render_template('thankyou1.html',
                               transaction_id=transaction_id,
                               outfit_name=outfit_name)
    else:
        # Update payment status to failed
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                '''UPDATE payments 
                   SET status = 'failed' 
                   WHERE transaction_id = ?''',
                (transaction_id,))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"Error updating payment status: {e}")
        
        return render_template('payment_failed.html',
                               transaction_id=transaction_id)


@app.route('/initiate_payment')
def initiate_payment():
    amount = request.args.get('amount', '10.00')
    purpose = request.args.get('purpose', 'VirtualTryOn')
    outfit_name = request.args.get('outfit', '')
    
    if 'user_id' not in session:
        return redirect(f"{FRONTEND_URL}/profile.html")
    
    transaction_id = f"TXN{uuid.uuid4().hex[:12].upper()}"
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''INSERT INTO payments (transaction_id, user_id, amount, purpose, status)
                 VALUES (?, ?, ?, ?, 'pending')''',
        (transaction_id, session['user_id'], float(amount), purpose))
    conn.commit()
    cursor.close()
    conn.close()
    
    upi_url = f"upi://pay?pa={UPI_ID}&pn={UPI_NAME}&am={amount}&cu=INR&tn={transaction_id}-{purpose}"
    
    return render_template('payment.html',
                           transaction_id=transaction_id,
                           amount=amount,
                           purpose=purpose,
                           outfit_name=outfit_name,
                           upi_url=upi_url,
                           upi_id=UPI_ID,
                           upi_name=UPI_NAME,
                           user_name=session.get('user_name', 'Friend'))


@app.route('/health')
def health():
    """Health check endpoint for Azure App Service"""
    try:
        conn = get_db_connection()
        conn.close()
        return jsonify({"status": "healthy", "database": "connected"}), 200
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
