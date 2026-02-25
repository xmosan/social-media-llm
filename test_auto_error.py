import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Load env vars
from dotenv import load_dotenv
load_dotenv()

from app.database import SessionLocal
from app.models import TopicAutomation

try:
    db = SessionLocal()
    autos = db.query(TopicAutomation).all()
    for a in autos:
        print(f"[{a.id}] {a.name} | Topic: {a.topic_prompt} | Last Error: {a.last_error}")
except Exception as e:
    print(f"DB Error: {e}")
