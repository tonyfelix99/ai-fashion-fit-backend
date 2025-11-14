# AI Fashion Fit – Smart Virtual Stylist

## Overview
AI Fashion Fit is a Flask-based web application that provides personalized outfit recommendations using Google Gemini AI. The app analyzes user photos to determine skin tone and body shape, then recommends complete outfit packages (top, bottom, and accessories) with separate purchase links for each item.

## Recent Changes (November 11, 2025)
- Initial project setup with Flask and Google Gemini integration
- Created complete application structure with all routes and templates
- Implemented outfit package system with separate items (top, bottom, accessories)
- Added lavender and cream color theme with Poppins font
- Configured UPI payment integration for micro-transactions
- Set up SQLite database for user profile storage

## Project Architecture

### Technology Stack
- **Backend**: Python 3.11 + Flask
- **Frontend**: HTML5 + Bootstrap 5 + Custom CSS
- **Database**: SQLite3
- **AI Integration**: Google Gemini 1.5 Pro (Vision + Text APIs)
- **Payment**: UPI deep-link integration

### File Structure
```
/
├── app.py                  # Main Flask application
├── outfits.json           # Outfit catalog with packages
├── fashion_fit.db         # SQLite database (auto-generated)
├── templates/
│   ├── index.html         # Landing page
│   ├── profile.html       # User information form
│   ├── recommendations.html  # Outfit recommendations display
│   ├── tryon_preview.html    # Virtual try-on preview
│   └── thankyou.html      # Thank you page
├── static/
│   ├── style.css          # Custom styling
│   ├── uploads/           # User uploaded photos
│   └── generated/         # AI-generated try-on images
```

### Routes
1. **`/`** - Landing page with hero section
2. **`/profile`** - User profile form (name, age, gender, photo upload)
3. **`/analyze`** - POST endpoint for AI photo analysis
4. **`/recommendations`** - Display filtered outfit packages
5. **`/tryon_preview`** - Virtual try-on with AI
6. **`/thankyou`** - Thank you page with tip option

### Key Features

#### 1. AI-Powered Analysis
- Uses Gemini Vision API to analyze user photos
- Determines skin tone (Fair/Wheatish/Dark)
- Identifies body shape (Slim/Average/Curvy)
- Stores results in SQLite database

#### 2. Smart Outfit Matching
Filters outfits based on:
- Gender
- Age group (e.g., 18-30, 25-45)
- Skin tone
- Body shape

#### 3. Complete Outfit Packages
Each recommendation includes:
- **Top**: Shirt, blouse, or upper garment
- **Bottom**: Pants, skirt, or lower garment
- **Accessories**: Jewelry, bags, shoes, etc.
- Individual "Buy" links for each item

#### 4. AI Personalization
- Gemini generates custom explanations for why each outfit suits the user
- One-sentence friendly descriptions based on user profile

#### 5. Virtual Try-On
- AI-powered preview combining user photo with outfit images
- Download and share functionality

#### 6. Monetization
- UPI payment buttons for virtual try-on (₹5)
- "Buy Me a Coffee" tip option (₹10)
- Affiliate links for each outfit item

### Database Schema

```sql
CREATE TABLE user_info (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    age INTEGER,
    gender TEXT,
    skin_tone TEXT,
    body_shape TEXT,
    image_path TEXT
);
```

### Environment Variables
- `GEMINI_API_KEY` - Google Gemini API key (required for AI features)
- `SESSION_SECRET` - Flask session secret key

### Outfit Catalog Format

Each outfit in `outfits.json` contains:
```json
{
  "name": "Outfit Name",
  "description": "Outfit description",
  "gender": "Male/Female",
  "skin_tones": ["Fair", "Wheatish", "Dark"],
  "body_shapes": ["Slim", "Average", "Curvy"],
  "age_group": "18-30",
  "items": {
    "top": {
      "name": "Item name",
      "price": "₹999",
      "link": "https://...",
      "image": "https://..."
    },
    "bottom": { ... },
    "accessories": { ... }
  }
}
```

## User Preferences
- No specific coding preferences noted yet
- Standard Flask application structure
- Bootstrap 5 for responsive UI
- Lavender (#c8a2c8) and Cream (#fffaf0) color scheme

## Future Extensions (Commented for Later)
1. Replace Gemini with TryOnDiffusion or Replicate for more realistic virtual try-on
2. Integrate real-time affiliate product API from Amazon/Myntra
3. Add multilingual support (English/Hindi)
4. Implement UPI payment webhook for transaction confirmation
5. Add user dashboard to view past recommendations and try-on history
6. Implement user authentication and saved preferences

## Development Notes
- Application runs on port 5000 with Flask development server
- Debug mode enabled for development
- SQLite database created automatically on first run
- Static files served from `/static` directory
- File uploads stored in `static/uploads/`
- Generated images saved to `static/generated/`

## Testing
To test the application:
1. Ensure `GEMINI_API_KEY` is set in environment
2. Navigate to home page and click "Start My Style Check"
3. Fill out profile form with name, age, gender, and upload a photo
4. View personalized outfit recommendations
5. Try virtual try-on feature for any outfit
6. Test individual buy links for tops, bottoms, and accessories

## Dependencies
- Flask - Web framework
- google-generativeai - Gemini AI SDK
- Pillow - Image processing
- requests - HTTP library for fetching images
- werkzeug - WSGI utilities
