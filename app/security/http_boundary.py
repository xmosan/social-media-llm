"""Request safeguards applied before parsers, authentication and route handlers."""
import asyncio
from urllib.parse import urlsplit

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
UPLOAD_PATHS = {"/media-assets", "/posts/intake", "/posts/preview_render", "/api/library/upload"}


def origin(value, *, referer=False):
    try:
        url = urlsplit(value)
        if (url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password
                or (not referer and (url.path not in ("", "/") or url.query or url.fragment))
                or any(c.isspace() for c in value)):
            return None
        return url.scheme, url.hostname.lower(), url.port or (443 if url.scheme == "https" else 80)
    except (ValueError, TypeError):
        return None


class HTTPBoundaryMiddleware:
    """Bound streamed bodies and enforce same-origin browser mutations.

    Cookie-free bearer/service clients remain usable. An Origin header, when
    present, must match even on anonymous login to prevent login CSRF. OAuth
    callbacks are GETs and retain their provider state/nonce validation.
    """
    def __init__(self, app, public_url, body_limit=2 * 1024 * 1024,
                 upload_limit=12 * 1024 * 1024, body_timeout=30):
        self.app, self.expected = app, origin(public_url)
        self.body_limit, self.upload_limit = body_limit, upload_limit
        self.body_timeout = body_timeout

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = Headers(scope=scope)
        method, path = scope["method"], scope["path"]

        async def secured_send(message):
            if message["type"] == "http.response.start":
                h = MutableHeaders(scope=message)
                h.setdefault("X-Content-Type-Options", "nosniff")
                h.setdefault("X-Frame-Options", "DENY")
                h.setdefault("Referrer-Policy", "no-referrer")
                h.setdefault("Content-Security-Policy",
                             "frame-ancestors 'none'; object-src 'none'; base-uri 'self'")
                h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
                if self.expected and self.expected[0] == "https":
                    h.setdefault("Strict-Transport-Security", "max-age=31536000")
                # Never cache account data, OAuth responses, or generated drafts.
                if not path.startswith(("/static/", "/uploads/")):
                    h["Cache-Control"] = "no-store"
            await send(message)

        async def reject(status, detail):
            await JSONResponse({"detail": detail}, status_code=status)(scope, receive, secured_send)

        if method not in SAFE_METHODS:
            supplied = headers.get("origin")
            if ((supplied is not None and origin(supplied) != self.expected)
                    or headers.get("sec-fetch-site") == "cross-site"):
                return await reject(403, "Open this page in Sabeel before continuing.")
            if supplied is None and ("access_token=" in headers.get("cookie", "")
                                     or "session=" in headers.get("cookie", "")
                                     or "owner_challenge=" in headers.get("cookie", "")):
                # Older same-origin browser clients may supply Referer instead.
                if origin(headers.get("referer", ""), referer=True) != self.expected:
                    return await reject(403, "Open this page in Sabeel before continuing.")

        limit = (self.upload_limit if path.rstrip("/") in UPLOAD_PATHS
                 or (path.startswith("/posts/") and path.endswith("/attach-media"))
                 else self.body_limit)
        length = headers.get("content-length")
        if length is not None:
            try:
                if int(length) < 0:
                    raise ValueError()
                if int(length) > limit:
                    return await reject(413, "This upload or request is too large.")
            except ValueError:
                return await reject(400, "Invalid request length.")
        # Buffer within the bound BEFORE parsers or handlers can perform work.
        # Enforcing only Content-Length would miss chunked requests.
        body = bytearray()
        async def read_body():
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return False
                body.extend(message.get("body", b""))
                if len(body) > limit:
                    return 413
                if not message.get("more_body", False):
                    return True
        try:
            result = await asyncio.wait_for(read_body(), timeout=self.body_timeout)
        except asyncio.TimeoutError:
            return await reject(408, "The upload timed out. Please try again.")
        if result is False:
            return
        if result == 413:
            return await reject(413, "This upload or request is too large.")
        delivered = False
        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()
        await self.app(scope, replay, secured_send)
