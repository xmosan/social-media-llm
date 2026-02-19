from app.config import settings

def check_env():
    print("--- Environment Diagnostic ---")
    
    variables = {
        "IG_ACCESS_TOKEN": settings.ig_access_token,
        "IG_USER_ID": settings.ig_user_id,
        "ADMIN_API_KEY": settings.admin_api_key,
        "BASE_URL": settings.public_base_url
    }
    
    for name, value in variables.items():
        if value is None:
            print(f"❌ {name}: NOT FOUND (is None)")
        elif value == "":
            print(f"⚠️ {name}: EMPTY STRING")
        else:
            # Mask the token for safety
            masked = value[:4] + "..." + value[-4:] if len(str(value)) > 10 else "***"
            print(f"✅ {name}: LOADED (Length: {len(str(value))}, Masked: {masked})")
            
    print("------------------------------")
    print("If variables are NOT FOUND, check your .env file format.")
    print("If they ARE LOADED but fail, your Token might be expired or copied incorrectly.")

if __name__ == "__main__":
    check_env()
