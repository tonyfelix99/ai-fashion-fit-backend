import os
import json
import pyodbc
import uuid
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
import google.generativeai as genai
from PIL import Image
import io
import jwt
from functools import wraps
from azure.storage.blob import BlobServiceClient, BlobSasPermissions, generate_blob_sas

app = Flask(__name__)
app.secret_key = os.environ.get('SESSION_SECRET', 'dev-secret-key-change-in-production')

# Environment Variables
FRONTEND_URL = os.environ.get('FRONTEND_URL', 'https://aifashionfitstorage.z30.web.core.windows.net')
JWT_SECRET = os.environ.get('JWT_SECRET', 'your-jwt-secret-change-in-production')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
UPI_ID = os.environ.get('UPI_ID', 'your-upi@bank')
UPI_NAME = os.environ.get('UPI_NAME', 'Your Name')

# Azure SQL Configuration
AZURE_SQL_SERVER = os.environ.get('AZURE_SQL_SERVER', '')
AZURE_SQL_DATABASE = os.environ.get('AZURE_SQL_DATABASE', '')
AZURE_SQL_USERNAME = os.environ.get('AZURE_SQL_USERNAME', '')
AZURE_SQL_PASSWORD = os.environ.get('AZURE_SQL_PASSWORD', '')

# Azure Blob Storage Configuration
AZURE_STORAGE_CONNECTION_STRING = os.environ.get('AZURE_STORAGE_CONNECTION_STRING', '')
AZURE_STORAGE_ACCOUNT_NAME = os.environ.get('AZURE_STORAGE_ACCOUNT_NAME', '')
AZURE_STORAGE_ACCOUNT_KEY = os.environ.get('AZURE_STORAGE_ACCOUNT_KEY', '')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# CORS Configuration
CORS(app, 
     origins=[FRONTEND_URL, "http://localhost:3000", "http://127.0.0.1:5500", "https://aifashionfitstorage.z30.web.core.windows.net"],
     supports_credentials=True,
     allow_headers=["Content-Type", "Authorization"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])

# Configure Gemini AI
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Initialize Blob Storage Client
blob_service_client = None
if AZURE_STORAGE_CONNECTION_STRING:
    try:
        blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
        print("✅ Connected to Azure Blob Storage")
    except Exception as e:
        print(f"⚠️ Could not connect to Blob Storage: {e}")


# ========== DATABASE FUNCTIONS ==========

def get_db_connection():
    """Create and return Azure SQL Database connection"""
    try:
        connection_string = (
            f"DRIVER={{ODBC Driver 18 for SQL Server}};"
            f"SERVER={AZURE_SQL_SERVER},1433;"
            f"DATABASE={AZURE_SQL_DATABASE};"
            f"UID={AZURE_SQL_USERNAME};"
            f"PWD={AZURE_SQL_PASSWORD};"
            f"Encrypt=yes;"
            f"TrustServerCertificate=yes;"
            f"Connection Timeout=60;"
        )
        conn = pyodbc.connect(connection_string)
        return conn
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        raise


def init_db():
    """Initialize database with all tables"""
    print("🔄 Initializing Azure SQL Database...")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Create user_info table
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
                    image_url NVARCHAR(500),
                    face_shape NVARCHAR(100) DEFAULT 'Oval',
                    hair_texture NVARCHAR(100) DEFAULT 'Straight',
                    hair_length NVARCHAR(50),
                    hair_color NVARCHAR(50),
                    hairstyle_suggestions NVARCHAR(MAX),
                    created_at DATETIME2 DEFAULT GETDATE(),
                    updated_at DATETIME2 DEFAULT GETDATE()
                )
            END
        ''')
        
        # Create payments table
        cursor.execute('''
            IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'payments')
            BEGIN
                CREATE TABLE payments (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    transaction_id NVARCHAR(100) UNIQUE NOT NULL,
                    user_id INT,
                    amount DECIMAL(10, 2),
                    purpose NVARCHAR(255),
                    outfit_name NVARCHAR(255),
                    status NVARCHAR(50) DEFAULT 'pending',
                    created_at DATETIME2 DEFAULT GETDATE(),
                    confirmed_at DATETIME2,
                    FOREIGN KEY (user_id) REFERENCES user_info(id)
                )
            END
        ''')
        
        # Create indexes
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
    print(f"⚠️ Warning: Could not initialize database: {e}")


# ========== JWT AUTHENTICATION ==========

def create_token(user_data):
    """Create JWT token for user"""
    payload = {
        'user_id': user_data['user_id'],
        'name': user_data.get('name', ''),
        'exp': datetime.utcnow() + timedelta(days=7)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')


def token_required(f):
    """Decorator to require valid JWT token"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        
        if not token:
            return jsonify({'error': 'Token missing'}), 401
        
        try:
            # Remove 'Bearer ' prefix if present
            if token.startswith('Bearer '):
                token = token[7:]
            
            data = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
            request.user_id = data['user_id']
            request.user_name = data.get('name', '')
            
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
        
        return f(*args, **kwargs)
    
    return decorated


# ========== BLOB STORAGE FUNCTIONS ==========

def upload_to_blob(file_data, filename, container_name='uploads'):
    """Upload file to Azure Blob Storage and return URL"""
    if not blob_service_client:
        print("⚠️ Blob storage not configured")
        return None
    
    try:
        # Ensure container exists
        try:
            container_client = blob_service_client.get_container_client(container_name)
            container_client.get_container_properties()
        except:
            container_client = blob_service_client.create_container(container_name)
            print(f"✅ Created container: {container_name}")
        
        # Upload blob
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=filename)
        blob_client.upload_blob(file_data, overwrite=True)
        
        # Return blob URL
        blob_url = blob_client.url
        print(f"✅ Uploaded to blob: {blob_url}")
        return blob_url
        
    except Exception as e:
        print(f"❌ Error uploading to blob: {e}")
        return None


def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ========== AI ANALYSIS FUNCTIONS ==========

def analyze_user_photo(image_data):
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
        img = Image.open(io.BytesIO(image_data))

        prompt = """Analyze this person's appearance comprehensively and return ONLY a JSON object with this exact format:
{
    "skin_tone": "Fair/Wheatish/Medium/Dark",
    "body_shape": "Slim/Average/Athletic/Curvy",
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
        print(f"❌ Error analyzing photo: {e}")
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
                "styling_tips": "Blow dry for volume"
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
        print(f"❌ Error generating hairstyle suggestions: {e}")
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
    """Match outfits based on user's profile"""
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
        print(f"❌ Error generating explanation: {e}")
        return f"This {outfit['name']} complements your style perfectly!"


# ========== API ROUTES ==========

@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint"""
    try:
        conn = get_db_connection()
        conn.close()
        
        blob_status = "connected" if blob_service_client else "not configured"
        gemini_status = "configured" if GEMINI_API_KEY else "not configured"
        
        return jsonify({
            "status": "healthy",
            "database": "connected",
            "blob_storage": blob_status,
            "gemini_ai": gemini_status,
            "timestamp": datetime.utcnow().isoformat()
        }), 200
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 500


@app.route('/api/analyze', methods=['POST'])
def api_analyze():
    """Analyze user photo and create profile"""
    try:
        # Get form data
        name = request.form.get('name')
        age = request.form.get('age')
        gender = request.form.get('gender')
        skin_tone = request.form.get('skin_tone')
        body_shape = request.form.get('body_shape')
        
        # Validate required fields
        if not all([name, age, gender, skin_tone, body_shape]):
            return jsonify({'error': 'Missing required fields'}), 400
        
        age = int(age)
        
        # Check for photo
        if 'photo' not in request.files:
            return jsonify({'error': 'No photo uploaded'}), 400
        
        file = request.files['photo']
        if not file.filename or file.filename == '':
            return jsonify({'error': 'No photo selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type. Use PNG, JPG, JPEG, or GIF'}), 400
        
        # Read file data
        file_data = file.read()
        
        # Generate unique filename
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        
        # Upload to blob storage
        image_url = upload_to_blob(file_data, unique_filename)
        
        if not image_url:
            return jsonify({'error': 'Failed to upload image'}), 500
        
        # Analyze photo with AI
        ai_analysis = analyze_user_photo(file_data)
        
        # Generate hairstyle suggestions
        hairstyle_data = generate_hairstyle_suggestions(ai_analysis, gender, age)
        
        # Save to database
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            '''INSERT INTO user_info (name, age, gender, skin_tone, body_shape, image_url, 
                                     face_shape, hair_texture, hair_length, hair_color, hairstyle_suggestions)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (name, age, gender, skin_tone, body_shape, image_url,
             ai_analysis.get('face_shape', 'Oval'),
             ai_analysis.get('hair_texture', 'Straight'),
             ai_analysis.get('current_hair_length', 'Medium'),
             ai_analysis.get('hair_color', 'Black'),
             json.dumps(hairstyle_data))
        )
        
        # Get inserted user ID
        cursor.execute('SELECT @@IDENTITY AS id')
        user_id = int(cursor.fetchone()[0])
        
        conn.commit()
        cursor.close()
        conn.close()
        
        # Create JWT token
        token = create_token({
            'user_id': user_id,
            'name': name
        })
        
        print(f"✅ User profile created: {name} (ID: {user_id})")
        
        return jsonify({
            'success': True,
            'token': token,
            'user': {
                'id': user_id,
                'name': name,
                'age': age,
                'gender': gender,
                'skin_tone': skin_tone,
                'body_shape': body_shape,
                'image_url': image_url,
                'face_shape': ai_analysis.get('face_shape'),
                'hair_texture': ai_analysis.get('hair_texture'),
                'hair_length': ai_analysis.get('current_hair_length'),
                'hair_color': ai_analysis.get('hair_color')
            },
            'hairstyles': hairstyle_data['suggestions']
        }), 201
        
    except Exception as e:
        print(f"❌ Error in analyze: {e}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500


@app.route('/api/user', methods=['GET'])
@token_required
def api_get_user():
    """Get user profile"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM user_info WHERE id = ?', (request.user_id,))
        row = cursor.fetchone()
        
        if not row:
            return jsonify({'error': 'User not found'}), 404
        
        # Parse hairstyle suggestions
        hairstyle_json = row[10] if row[10] else '{"suggestions": []}'
        hairstyle_data = json.loads(hairstyle_json)
        
        user_data = {
            'id': row[0],
            'name': row[1],
            'age': row[2],
            'gender': row[3],
            'skin_tone': row[4],
            'body_shape': row[5],
            'image_url': row[6],
            'face_shape': row[7],
            'hair_texture': row[8],
            'hair_length': row[9] if len(row) > 9 else 'Medium',
            'hair_color': row[10] if len(row) > 10 else 'Black',
            'hairstyles': hairstyle_data.get('suggestions', [])
        }
        
        cursor.close()
        conn.close()
        
        return jsonify(user_data), 200
        
    except Exception as e:
        print(f"❌ Error getting user: {e}")
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/recommendations', methods=['GET'])
@token_required
def api_recommendations():
    """Get outfit recommendations for user"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM user_info WHERE id = ?', (request.user_id,))
        row = cursor.fetchone()
        
        if not row:
            return jsonify({'error': 'User not found'}), 404
        
        user = {
            'name': row[1],
            'age': row[2],
            'gender': row[3],
            'skin_tone': row[4],
            'body_shape': row[5],
            'image_url': row[6],
            'face_shape': row[7],
            'hair_texture': row[8]
        }
        
        cursor.close()
        conn.close()
        
        # Get matched outfits
        matched_outfits = match_outfits(user)
        
        # Add AI explanations
        outfits_with_explanations = []
        for outfit in matched_outfits:
            explanation = explain_match(user, outfit)
            outfit_copy = outfit.copy()
            outfit_copy['explanation'] = explanation
            outfits_with_explanations.append(outfit_copy)
        
        return jsonify({
            'user': user,
            'outfits': outfits_with_explanations,
            'upi_id': UPI_ID,
            'upi_name': UPI_NAME
        }), 200
        
    except Exception as e:
        print(f"❌ Error getting recommendations: {e}")
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/hairstyles', methods=['GET'])
@token_required
def api_hairstyles():
    """Get hairstyle suggestions for user"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT hairstyle_suggestions, face_shape, hair_texture FROM user_info WHERE id = ?', 
                      (request.user_id,))
        row = cursor.fetchone()
        
        if not row:
            return jsonify({'error': 'User not found'}), 404
        
        hairstyle_json = row[0] if row[0] else '{"suggestions": []}'
        hairstyle_data = json.loads(hairstyle_json)
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'hairstyles': hairstyle_data.get('suggestions', []),
            'face_shape': row[1],
            'hair_texture': row[2]
        }), 200
        
    except Exception as e:
        print(f"❌ Error getting hairstyles: {e}")
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/payment/initiate', methods=['POST'])
@token_required
def api_initiate_payment():
    """Initiate payment transaction"""
    try:
        data = request.get_json()
        amount = float(data.get('amount', 10.00))
        purpose = data.get('purpose', 'VirtualTryOn')
        outfit_name = data.get('outfit_name', '')
        
        # Generate transaction ID
        transaction_id = f"TXN{uuid.uuid4().hex[:12].upper()}"
        
        # Save to database
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            '''INSERT INTO payments (transaction_id, user_id, amount, purpose, outfit_name, status)
               VALUES (?, ?, ?, ?, ?, 'pending')''',
            (transaction_id, request.user_id, amount, purpose, outfit_name)
        )
        conn.commit()
        cursor.close()
        conn.close()
        
        # Generate UPI URL
        upi_url = f"upi://pay?pa={UPI_ID}&pn={UPI_NAME}&am={amount}&cu=INR&tn={transaction_id}-{purpose}"
        
        print(f"💳 Payment initiated: {transaction_id} for ₹{amount}")
        
        return jsonify({
            'success': True,
            'transaction_id': transaction_id,
            'amount': amount,
            'purpose': purpose,
            'outfit_name': outfit_name,
            'upi_url': upi_url,
            'upi_id': UPI_ID,
            'upi_name': UPI_NAME
        }), 201
        
    except Exception as e:
        print(f"❌ Error initiating payment: {e}")
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/payment/confirm', methods=['POST'])
@token_required
def api_confirm_payment():
    """Confirm payment completion"""
    try:
        data = request.get_json()
        transaction_id = data.get('transaction_id')
        paid = data.get('paid', False)
        
        if not transaction_id:
            return jsonify({'error': 'Transaction ID required'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if paid:
            # Mark as confirmed
            cursor.execute(
                '''UPDATE payments 
                   SET status = 'confirmed', confirmed_at = GETDATE() 
                   WHERE transaction_id = ? AND user_id = ?''',
                (transaction_id, request.user_id)
            )
            status = 'confirmed'
            message = 'Payment confirmed successfully'
        else:
            # Mark as failed
            cursor.execute(
                '''UPDATE payments 
                   SET status = 'failed' 
                   WHERE transaction_id = ? AND user_id = ?''',
                (transaction_id, request.user_id)
            )
            status = 'failed'
            message = 'Payment marked as failed'
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print(f"💳 Payment {status}: {transaction_id}")
        
        return jsonify({
            'success': True,
            'transaction_id': transaction_id,
            'status': status,
            'message': message
        }), 200
        
    except Exception as e:
        print(f"❌ Error confirming payment: {e}")
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/payment/status/<transaction_id>', methods=['GET'])
@token_required
def api_payment_status(transaction_id):
    """Check payment status"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            'SELECT status, amount, purpose, outfit_name, created_at, confirmed_at FROM payments WHERE transaction_id = ? AND user_id = ?',
            (transaction_id, request.user_id)
        )
        row = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        if not row:
            return jsonify({'error': 'Transaction not found'}), 404
        
        return jsonify({
            'transaction_id': transaction_id,
            'status': row[0],
            'amount': float(row[1]),
            'purpose': row[2],
            'outfit_name': row[3],
            'created_at': row[4].isoformat() if row[4] else None,
            'confirmed_at': row[5].isoformat() if row[5] else None
        }), 200
        
    except Exception as e:
        print(f"❌ Error checking payment status: {e}")
        return jsonify({'error': 'Server error'}), 500


# ========== ERROR HANDLERS ==========

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500


# ========== MAIN ==========

if __name__ == '__main__':
    print("\n" + "="*50)
    print("🚀 Fashion Fit AI Backend API")
    print("="*50)
    print(f"Frontend URL: {FRONTEND_URL}")
    print(f"Gemini AI: {'✅ Configured' if GEMINI_API_KEY else '❌ Not configured'}")
    print(f"Blob Storage: {'✅ Connected' if blob_service_client else '❌ Not configured'}")
    print("="*50 + "\n")
    
    app.run(host='0.0.0.0', port=8000, debug=False)