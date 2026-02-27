import os
import uvicorn
from dotenv import load_dotenv

def main():
    # Force absolute path to avoid confusion
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    dotenv_path = os.path.join(base_dir, '.env')
    print(f"Loading env from {dotenv_path}...")
    load_dotenv(dotenv_path)
    
    # Ensure DATABASE_URL is set and starts with postgresql://
    db_url = os.environ.get("DATABASE_URL")
    print(f"DATABASE_URL: {db_url[:20]}..." if db_url else "DATABASE_URL: NOT FOUND")
    
    if db_url and db_url.startswith("postgres://"):
        os.environ["DATABASE_URL"] = db_url.replace("postgres://", "postgresql://", 1)
        
    print(f"Starting app at http://0.0.0.0:8000")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)

if __name__ == "__main__":
    main()
