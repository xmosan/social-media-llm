from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
pwd_context.hash("A"*100)
print("Hash A")
pwd_context.hash("A"*72)
print("Hash B")
