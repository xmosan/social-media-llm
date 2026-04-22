
from app.db import SessionLocal
from app.services.automation_runner import run_automation_once
from app.models import TopicAutomation

def test_run():
    db = SessionLocal()
    # Find the automation that failed (id=32 from previous logs or any active one)
    auto = db.query(TopicAutomation).filter(TopicAutomation.enabled == True).first()
    if not auto:
        print("No active automation found.")
        return
    
    print(f"Testing automation id={auto.id} ({auto.name})")
    try:
        post = run_automation_once(db, auto.id, force_publish=True)
        if post:
            print(f"SUCCESS: Created post {post.id} with status {post.status}")
        else:
            print("FAILURE: run_automation_once returned None")
    except Exception as e:
        print(f"CRASH: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    test_run()
