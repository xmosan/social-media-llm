import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import engine, SessionLocal
from .models import Base
from .services.scheduler import start_scheduler
from .routes.posts import router as posts_router
from .routes.admin import router as admin_router


app = FastAPI(title="Social Poster MVP", version="0.2.0")

@app.get("/")
def root():
    return {"status": "Social Media LLM API is running"}

@app.get("/debug/ping")
def debug_ping():
    return {"ok": True}

# uploads
os.makedirs(settings.uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.uploads_dir), name="uploads")

# routers
app.include_router(posts_router)
app.include_router(admin_router)

@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    try:
        app.state.scheduler = start_scheduler(SessionLocal)
    except Exception as e:
        print("Scheduler start failed:", repr(e))
        app.state.scheduler = None

@app.on_event("shutdown")
def on_shutdown():
    sched = getattr(app.state, "scheduler", None)
    if sched:
        try:
            sched.shutdown(wait=False)
        except Exception:
            pass