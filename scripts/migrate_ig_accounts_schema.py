import os
import sys
from sqlalchemy import text

# Add the parent directory to sys.path to allow importing from app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import engine

def migrate():
    print("Checking for profile_picture_url column in ig_accounts table...")
    with engine.connect() as conn:
        # Check if the column exists
        if engine.dialect.name == 'postgresql':
            query = text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='ig_accounts' AND column_name='profile_picture_url';
            """)
        else: # sqlite
            query = text("PRAGMA table_info(ig_accounts)")
            
        result = conn.execute(query)
        columns = [row[0] if engine.dialect.name == 'postgresql' else row[1] for row in result.fetchall()]
        
        if 'profile_picture_url' not in columns:
            print("Column 'profile_picture_url' not found. Adding it now...")
            try:
                conn.execute(text("ALTER TABLE ig_accounts ADD COLUMN profile_picture_url TEXT;"))
                conn.commit()
                print("Column added successfully.")
            except Exception as e:
                print(f"Error adding column: {e}")
        else:
            print("Column 'profile_picture_url' already exists.")

if __name__ == "__main__":
    migrate()
