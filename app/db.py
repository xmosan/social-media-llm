import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Use absolute path for SQLite to avoid permission issues with relative paths in some environments
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# We'll use a new DB name to avoid blocked "app.db" if it has OS-level locks
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "saas.db")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH}")

# Railway often provides postgres:// but SQLAlchemy wants postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

# SQLite needs a special flag
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

print(f"Connecting to DB: {DATABASE_URL}")
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)

# Enable WAL mode for SQLite to prevent "database is locked" errors during concurrent access
if DATABASE_URL.startswith("sqlite"):
    from sqlalchemy import event
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()