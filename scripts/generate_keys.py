"""Print fresh .env API_KEYS configuration. Does not overwrite existing files."""
import json
import secrets

print("API_KEYS=" + json.dumps({
    secrets.token_urlsafe(32): {"user_id":"demo-user", "role":"user"},
    secrets.token_urlsafe(32): {"user_id":"operator", "role":"admin"},
}, separators=(",", ":")))
