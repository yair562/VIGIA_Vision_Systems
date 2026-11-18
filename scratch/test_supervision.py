import urllib.request
import ssl
import json
import http.cookiejar

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj), urllib.request.HTTPSHandler(context=ctx))

# Login
login_url = "https://127.0.0.1:5001/api/v1/auth/login"
payload = json.dumps({"username": "admin_dev", "password": "AdminDev2026!"}).encode("utf-8")
req = urllib.request.Request(login_url, data=payload, headers={"Content-Type": "application/json"})

res = opener.open(req, timeout=5)
print("LOGIN:", res.status)

sup_url = "https://127.0.0.1:5001/api/v1/supervision/status"
req_sup = urllib.request.Request(sup_url)
res_sup = opener.open(req_sup, timeout=5)
print("SUPERVISION STATUS:", res_sup.status)
data = json.loads(res_sup.read().decode())
print(json.dumps(data, indent=2))
