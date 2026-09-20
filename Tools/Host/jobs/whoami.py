"""Print only the Codex account identity from a container's auth.json.

Never prints a token. Reads in place; copies nothing out of the volume.
"""
import base64
import json
import os

CANDIDATES = [
    "/root/.codex/auth.json",
    os.path.expanduser("~/.codex/auth.json"),
    "/home/node/.codex/auth.json",
    "/config/.codex/auth.json",
]

path = next((p for p in CANDIDATES if os.path.exists(p)), None)
if not path:
    print("auth.json not found in:", ", ".join(CANDIDATES))
    raise SystemExit(1)

print("file:", path)

with open(path, encoding="utf-8-sig") as fh:
    data = json.load(fh)

tokens = data.get("tokens") or {}

# A top-level email is sometimes present and is the cheapest answer.
for key in ("email", "account_email"):
    if data.get(key):
        print("email:", data[key])

jwt = next(
    (v for v in tokens.values() if isinstance(v, str) and v.count(".") == 2),
    None,
)
if not jwt:
    print("no JWT in tokens; keys present:", ", ".join(sorted(tokens)))
    raise SystemExit(0)

payload = jwt.split(".")[1]
payload += "=" * (-len(payload) % 4)
claims = json.loads(base64.urlsafe_b64decode(payload))

auth = claims.get("https://api.openai.com/auth") or {}
print("email:", claims.get("email"))
print("name :", claims.get("name"))
print("plan :", auth.get("chatgpt_plan_type"))
print("acct :", auth.get("chatgpt_account_id"))
