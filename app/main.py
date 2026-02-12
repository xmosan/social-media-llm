import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import engine, SessionLocal, Base
from .routes.posts import router as posts_router
from .services.scheduler import start_scheduler

app = FastAPI(title="Social Poster MVP", version="0.2.0")

@app.get("/")
def root():
    return {"status": "Social Media LLM API is running"}

Base.metadata.create_all(bind=engine)
app.include_router(posts_router)

# Serve /uploads publicly (needed for Instagram image_url)
os.makedirs(settings.uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.uploads_dir), name="uploads")

def db_factory():
    return SessionLocal()

@app.on_event("startup")
def on_startup():
    app.state.scheduler = start_scheduler(db_factory)

@app.on_event("shutdown")
def on_shutdown():
    sched = getattr(app.state, "scheduler", None)
    if sched:
        sched.shutdown(wait=False)