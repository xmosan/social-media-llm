import sys
import os

# Set dummy key since .env isn't readable, if the system tries to load it, we'll see
os.environ["OPENAI_API_KEY"] = "sk-proj-test"

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.services.llm import generate_topic_caption

try:
    print("Testing generate_topic_caption...")
    res = generate_topic_caption("Ramadan preparation", style="islamic_reminder", tone="uplifting")
    print(res)
except Exception as e:
    import traceback
    print(f"LLM Error: {e}")
    traceback.print_exc()

