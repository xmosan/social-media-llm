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
  <style>
    body { font-family: -apple-system, system-ui, Segoe UI, Roboto, Arial; margin: 24px; }
    h1 { margin: 0 0 8px; }
    .row { display: flex; gap: 16px; flex-wrap: wrap; }
    .card { border: 1px solid #ddd; border-radius: 10px; padding: 14px; max-width: 520px; flex: 1; min-width: 320px; }
    input, textarea, select, button { font: inherit; }
    textarea { width: 100%; min-height: 90px; }
    input[type="file"] { width: 100%; }
    button { padding: 8px 12px; border-radius: 8px; border: 1px solid #ccc; background: #fff; cursor: pointer; }
    button.primary { background: #111; color: #fff; border-color: #111; }
    .muted { color: #666; font-size: 0.92em; }
    .pill { display:inline-block; padding: 2px 8px; border:1px solid #ddd; border-radius: 999px; font-size: 0.85em; }
    .list { display: grid; gap: 10px; }
    .post { border: 1px solid #eee; border-radius: 10px; padding: 12px; }
    .post h3 { margin: 0 0 6px; font-size: 1.05em; }
    .post pre { white-space: pre-wrap; word-break: break-word; background: #fafafa; padding: 10px; border-radius: 8px; border: 1px solid #eee; }
    .actions { display:flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }
    .topbar { display:flex; gap: 12px; align-items: center; flex-wrap: wrap; margin: 12px 0 8px; }
    .right { margin-left:auto; }
    .ok { color: #0a7; }
    .err { color: #c00; white-space: pre-wrap; }
    .img { max-width: 100%; border-radius: 10px; border: 1px solid #eee; }
  </style>
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
