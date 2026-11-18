import http.cookiejar
import json
import os
import ssl
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from dotenv import dotenv_values
import psycopg2

ROOT = Path(r"C:\GEST.PROY.TI\Software\VIGIA_Vision_Systems")
OUT_JSON = ROOT / "experiments" / "vision_07b" / "results" / "fase_e_live_snapshot.json"
OUT_JSON.parent.mkdir(parents=True, exist_ok=True)

# 1. API Live Status (Read-Only GETs)
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(cj),
    urllib.request.HTTPSHandler(context=ctx),
)

opener.open(
    urllib.request.Request(
        "https://127.0.0.1:5001/api/v1/auth/login",
        data=json.dumps({"username": "admin_dev", "password": "AdminDev2026!"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    ),
    timeout=5,
)

def get_json(url):
    with opener.open(url, timeout=5) as r:
        return json.loads(r.read().decode("utf-8"))

sup = get_json("https://127.0.0.1:5001/api/v1/supervision/status")
cams = get_json("https://127.0.0.1:5001/api/v1/cameras")
cam_ent = get_json("https://127.0.0.1:5001/api/v1/cameras/CAM-ENTRADA/status")
cam_sal = get_json("https://127.0.0.1:5001/api/v1/cameras/CAM-SALIDA/status")

# 2. GPU / VRAM Telemetry
gpu_csv = subprocess.check_output(
    [
        "nvidia-smi",
        "--query-gpu=timestamp,name,memory.total,memory.used,memory.free,utilization.gpu,utilization.memory,temperature.gpu,power.draw",
        "--format=csv,noheader,nounits",
    ],
    text=True,
).strip()

# 3. Process verification
ps_out = subprocess.check_output(
    [
        "powershell",
        "-NoProfile",
        "-Command",
        "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Select-Object ProcessId,ParentProcessId,CommandLine | ConvertTo-Json",
    ],
    text=True,
).strip()

# 4. PostgreSQL Read-Only Stats (zero mutations)
env = dotenv_values(r"C:\GEST.PROY.TI\Software\.env")
conn = psycopg2.connect(
    host=env["POSTGRES_HOST"],
    port=env["POSTGRES_PORT"],
    dbname=env["POSTGRES_DB"],
    user=env["POSTGRES_USER"],
    password=env["POSTGRES_PASSWORD"],
)
cur = conn.cursor()

cur.execute("""
SELECT c.codigo, d.tipo_vehiculo_pred, COUNT(*)::int,
       ROUND(MIN(d.confianza_vehiculo)::numeric, 4)::float8,
       ROUND(MAX(d.confianza_vehiculo)::numeric, 4)::float8,
       ROUND(AVG(d.confianza_vehiculo)::numeric, 4)::float8,
       MIN(d.fecha_hora)::text, MAX(d.fecha_hora)::text
FROM deteccion d
JOIN area_vision av ON av.id_area_vision = d.id_area_vision
JOIN camara c ON c.id_camara = av.id_camara
GROUP BY 1, 2
ORDER BY 1, 3 DESC;
""")
db_all_summary = [
    {
        "camera_code": r[0], "vehicle_type": r[1], "count": r[2],
        "min_conf": r[3], "max_conf": r[4], "avg_conf": r[5],
        "first_ts": r[6], "last_ts": r[7],
    }
    for r in cur.fetchall()
]

cur.execute("""
SELECT c.codigo, d.tipo_vehiculo_pred, COUNT(*)::int,
       ROUND(MIN(d.confianza_vehiculo)::numeric, 4)::float8,
       ROUND(MAX(d.confianza_vehiculo)::numeric, 4)::float8,
       ROUND(AVG(d.confianza_vehiculo)::numeric, 4)::float8,
       MIN(d.fecha_hora)::text, MAX(d.fecha_hora)::text
FROM deteccion d
JOIN area_vision av ON av.id_area_vision = d.id_area_vision
JOIN camara c ON c.id_camara = av.id_camara
WHERE d.ruta_evidencia_foto LIKE '20261117%%'
GROUP BY 1, 2
ORDER BY 1, 3 DESC;
""")
db_20261117_summary = [
    {
        "camera_code": r[0], "vehicle_type": r[1], "count": r[2],
        "min_conf": r[3], "max_conf": r[4], "avg_conf": r[5],
        "first_ts": r[6], "last_ts": r[7],
    }
    for r in cur.fetchall()
]

cur.execute("""
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'deteccion'
ORDER BY ordinal_position;
""")
deteccion_schema = [
    {"column": r[0], "type": r[1], "nullable": r[2], "default": r[3]}
    for r in cur.fetchall()
]

cur.execute("SELECT COUNT(*)::int FROM deteccion;")
total_db_rows = cur.fetchone()[0]
conn.close()

payload = {
    "captured_utc": datetime.now(timezone.utc).isoformat(),
    "gpu_smi": gpu_csv,
    "python_processes": json.loads(ps_out) if ps_out else [],
    "supervision_status": sup,
    "cameras": cams,
    "cam_entrada_status": cam_ent,
    "cam_salida_status": cam_sal,
    "postgresql_read_only": {
        "total_rows": total_db_rows,
        "deteccion_columns": deteccion_schema,
        "summary_all_dates": db_all_summary,
        "summary_20261117": db_20261117_summary,
    },
}

OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
print("Saved snapshot to", OUT_JSON)
print("GPU:", gpu_csv)
print("Supervision Status:", json.dumps(sup, indent=2, ensure_ascii=False))
print("CAM-ENTRADA:", json.dumps(cam_ent, indent=2, ensure_ascii=False))
print("CAM-SALIDA:", json.dumps(cam_sal, indent=2, ensure_ascii=False))
print("DB 20261117:", db_20261117_summary)
