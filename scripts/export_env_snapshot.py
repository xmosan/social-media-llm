import os
import json
import base64
from cryptography.fernet import Fernet
from datetime import datetime
from dotenv import load_dotenv

def export_env_snapshot():
    # Load .env into os.environ
    load_dotenv()
    
    env_keys = list(os.environ.keys())
    
    backup_key = os.environ.get("ENV_BACKUP_KEY")
    if not backup_key:
        print("ERROR: ENV_BACKUP_KEY is not set.")
        return
        
    try:
        f = Fernet(backup_key.encode('utf-8'))
    except Exception as e:
        print(f"ERROR: Invalid ENV_BACKUP_KEY formatting. Must be valid Fernet base64 key: {e}")
        print("You can generate one using: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"")
        return
        
    data = {
        "timestamp": datetime.now().isoformat(),
        "keys": env_keys
    }
    
    json_data = json.dumps(data)
    encrypted_data = f.encrypt(json_data.encode('utf-8'))
    
    timestamp_str = datetime.now().strftime("%Y_%m_%d_%H%M")
    filename = f"env_snapshot_{timestamp_str}.enc"
    
    out_dir = os.path.join(os.getcwd(), "backups")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, filename)
    
    with open(out_path, "wb") as file_out:
        file_out.write(encrypted_data)
        
    print(f"SUCCESS: Environment snapshot encrypted and saved to {out_path}")

if __name__ == "__main__":
    export_env_snapshot()
