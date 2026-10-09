"""Carry an authorized workspace across async requests and sync provider calls.

The ASGI task owns a fresh mutable scope. FastAPI's sync dependency and endpoint
workers inherit that same object; setting a ContextVar inside a worker alone
would not propagate back to the request. Background jobs use their own scope.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass
class UsageScope:
    org_id: int | None = None


current_scope: ContextVar[UsageScope | None] = ContextVar("sabeel_usage_scope", default=None)


@contextmanager
def workspace_usage(org_id=None):
    token = current_scope.set(UsageScope(org_id=org_id))
    try:
        yield
    finally:
        current_scope.reset(token)


def bind_workspace(org_id: int) -> int:
    scope = current_scope.get()
    if scope is not None:
        scope.org_id = org_id
    return org_id


class UsageContextMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        with workspace_usage():
            await self.app(scope, receive, send)
