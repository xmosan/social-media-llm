from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/admin", tags=["admin"])

HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Social Media LLM Admin</title>
</head>
<body>
  <h1>🚀 Social Media LLM Admin</h1>
  <p>If you see this, the real admin GUI is loading.</p>
</body>
</html>
"""

# ✅ IMPORTANT: with prefix="/admin", this is the correct path for "/admin"
@router.get("", response_class=HTMLResponse)
def admin_page():
    return HTML
