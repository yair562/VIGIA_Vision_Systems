import sys
from pathlib import Path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

from VIGIA_Core.repository.user_repository import resolve_database_dsn
import psycopg2

conn = psycopg2.connect(resolve_database_dsn())
with conn.cursor() as cur:
    cur.execute("SELECT id_camara, codigo, nombre, uri_stream, activa FROM camara;")
    print("CAMARAS:")
    for row in cur.fetchall():
        print(" ", row)
    cur.execute("SELECT id_area_vision, id_camara, codigo, nombre, tipo_movimiento, activa FROM area_vision;")
    print("AREAS:")
    for row in cur.fetchall():
        print(" ", row)
conn.close()
