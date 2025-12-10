import os
import json
import uuid
import platform
from datetime import datetime
from urllib import request, error

# 1. READ CONFIG
API_KEY = os.getenv("JNKN_POSTHOG_API_KEY")
HOST = os.getenv("JNKN_POSTHOG_HOST", "https://app.posthog.com")

print(f"--- DIAGNOSTICS ---")
print(f"API Key Present: {bool(API_KEY)}")
if API_KEY:
    print(f"API Key Preview: {API_KEY[:8]}...")
print(f"Target Host: {HOST}")

if not API_KEY:
    print("❌ STOPPING: No API Key found in environment.")
    exit(1)

# 2. PREPARE PAYLOAD
payload = {
    "api_key": API_KEY,
    "event": "manual_debug_event",
    "properties": {
        "distinct_id": str(uuid.uuid4()),
        "$lib": "jnkn-debug",
        "$os": platform.system(),
        "timestamp": datetime.utcnow().isoformat()
    }
}

# 3. SEND REQUEST (Verbose)
print("\n--- SENDING REQUEST ---")
try:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{HOST}/capture/",
        data=data,
        headers={"Content-Type": "application/json"}
    )
    
    with request.urlopen(req, timeout=5.0) as response:
        print(f"✅ STATUS: {response.status}")
        print(f"✅ REASON: {response.reason}")
        print(f"✅ BODY: {response.read().decode('utf-8')}")
        
except error.HTTPError as e:
    print(f"❌ HTTP ERROR: {e.code} {e.reason}")
    print(f"❌ BODY: {e.read().decode('utf-8')}")
except error.URLError as e:
    print(f"❌ NETWORK ERROR: {e.reason}")
except Exception as e:
    print(f"❌ UNKNOWN ERROR: {type(e).__name__}: {e}")