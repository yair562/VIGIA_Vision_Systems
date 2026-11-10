import urllib3
import requests
from pathlib import Path

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

key = "jY3mSVrz6yLWppIU0NxjBuhuh3zrLypAdUJYBDZQFHo"
bus_path = Path(r"C:\GEST.PROY.TI\Software\VIGIA_Vision_Systems\evidencias_vigia\20261105\CAM-ENTRADA\20261105T052002_513609Z_bccec26ad762_orig.jpg")
with open(bus_path, "rb") as f:
    jpeg_bytes = f.read()

for cam in ["CAM-ENTRADA", "CAM-SALIDA", "CAM-03", "CAM-04"]:
    url = f"https://127.0.0.1:5000/api/v1/cameras/{cam}/push"
    headers = {"Content-Type": "image/jpeg", "X-Camera-Key": key, "X-Request-Id": f"test_{cam}"}
    r = requests.post(url, data=jpeg_bytes, headers=headers, verify=False, timeout=10)
    print(f"{cam}: status={r.status_code}, ok={r.json().get('ok')}, id={r.json().get('id_deteccion')}")
