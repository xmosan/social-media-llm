"""Discard credential-bearing cookies left by the previous Instagram flow."""
from urllib.parse import urlsplit
from starlette.middleware.base import BaseHTTPMiddleware
from app.config import settings


class LegacyInstagramSessionCleanup(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request.session.pop("temp_ig_token", None)
        request.session.pop("discovered_accounts", None)
        response = await call_next(request)
        if request.url.path.startswith(("/auth/instagram", "/auth/meta", "/accounts/", "/ig-accounts")):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Referrer-Policy"] = "no-referrer"
        if "temp_ig_token" in request.cookies:
            response.delete_cookie("temp_ig_token", path="/", secure=True, httponly=True, samesite="lax")
            response.delete_cookie("temp_ig_token", path="/", domain=urlsplit(settings.public_base_url).hostname,
                                   secure=True, httponly=True, samesite="lax")
        return response
