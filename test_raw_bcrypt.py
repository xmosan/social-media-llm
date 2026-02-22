import bcrypt

def verify_password(plain_password: str, hashed_password: str) -> bool:
    # Handle the fact that passwords could be > 72 bytes. Bcrypt limit is 72 bytes.
    # To be safe, we truncate or hash it first. Let's just truncate.
    return bcrypt.checkpw(plain_password.encode('utf-8')[:72], hashed_password.encode('utf-8'))

def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8')[:72], bcrypt.gensalt()).decode('utf-8')

hash = get_password_hash("test_password_123")
print("Hash:", hash)
print("Verify:", verify_password("test_password_123", hash))
