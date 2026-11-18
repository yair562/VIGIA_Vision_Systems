import urllib.request
import ssl
import json
import http.cookiejar
import sys

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj), urllib.request.HTTPSHandler(context=ctx))

# Login
login_url = "https://127.0.0.1:5001/api/v1/auth/login"
payload = json.dumps({"username": "admin_dev", "password": "AdminDev2026!"}).encode("utf-8")
req = urllib.request.Request(login_url, data=payload, headers={"Content-Type": "application/json"})

try:
    res = opener.open(req, timeout=5)
    print("LOGIN STATUS:", res.status)
    print("LOGIN RESPONSE:", res.read().decode())
except Exception as e:
    print("LOGIN FAILED:", e)
    sys.exit(1)

endpoints = [
    "/api/v1/cameras",
    "/api/v1/devices/usb-cameras",
    "/api/v1/cameras/CAM-ENTRADA/status",
    "/api/v1/cameras/CAM-SALIDA/status",
]

for ep in endpoints:
    url = f"https://127.0.0.1:5001{ep}"
    try:
        r = opener.open(url, timeout=5)
        print(f"\n=== [OK {r.status}] {ep} ===")
        data = json.loads(r.read().decode())
        print(json.dumps(data, indent=2))
    except Exception as e:
        print(f"\n=== [ERR] {ep} -> {e} ===")
