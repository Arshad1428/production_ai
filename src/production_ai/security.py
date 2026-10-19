import secrets
import time
from collections import defaultdict, deque
from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyHeader

key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def principal(request: Request, key: str | None = Depends(key_header)):
    if key:
        for expected, identity in request.app.state.settings.api_keys.items():
            if secrets.compare_digest(key.encode(), expected.encode()):
                return identity
    raise HTTPException(401, "Invalid or missing API key")

def admin(identity=Depends(principal)):
    if identity.role != "admin":
        raise HTTPException(403, "Administrator role required")
    return identity

class RateLimiter:
    def __init__(self, limit):
        self.limit = limit
        self.events = defaultdict(deque)

    def check(self, owner):
        now = time.monotonic()
        q = self.events[owner]
        while q and q[0] <= now-60:
            q.popleft()
        if len(q) >= self.limit:
            raise HTTPException(429, "Rate limit exceeded", headers={"Retry-After":"60"})
        q.append(now)
