from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/admin", tags=["admin"])

HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Social Media LLM Admin</title>
  <style>
    body { font-family: -apple-system, system-ui, Segoe UI, Roboto, Arial; margin: 24px; }
    h1 { margin: 0 0 8px; }
    .muted { color: #666; font-size: 0.92em; }
  </style>
</head>
<body>
  <h1>🚀 Social Media LLM Admin</h1>
  <div class="muted">GUI loaded ✅</div>
</body>
</html>
"""

@router.get("", response_class=HTMLResponse)
def admin_page():
    return HTML