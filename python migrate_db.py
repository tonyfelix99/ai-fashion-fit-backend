#!/usr/bin/env python3
"""
Database Migration Script
Run this once to add new columns to existing database
"""

import sqlite3


def migrate_database():
    print("🔄 Starting database migration...")

    conn = sqlite3.connect('fashion_fit.db')
    c = conn.cursor()

    # Add face_shape column
    try:
        c.execute(
            "ALTER TABLE user_info ADD COLUMN face_shape TEXT DEFAULT 'Oval'")
        print("✅ Added face_shape column")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("ℹ️  face_shape column already exists")
        else:
            print(f"⚠️  Error adding face_shape: {e}")

    # Add hair_texture column
    try:
        c.execute(
            "ALTER TABLE user_info ADD COLUMN hair_texture TEXT DEFAULT 'Straight'"
        )
        print("✅ Added hair_texture column")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("ℹ️  hair_texture column already exists")
        else:
            print(f"⚠️  Error adding hair_texture: {e}")

    # Add hairstyle_suggestions column
    try:
        c.execute(
            "ALTER TABLE user_info ADD COLUMN hairstyle_suggestions TEXT")
        print("✅ Added hairstyle_suggestions column")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("ℹ️  hairstyle_suggestions column already exists")
        else:
            print(f"⚠️  Error adding hairstyle_suggestions: {e}")

    conn.commit()

    # Verify columns
    c.execute("PRAGMA table_info(user_info)")
    columns = c.fetchall()

    print("\n📊 Current user_info table structure:")
    for col in columns:
        print(f"   - {col[1]} ({col[2]})")

    conn.close()
    print("\n✨ Migration complete!")


if __name__ == "__main__":
    migrate_database()
