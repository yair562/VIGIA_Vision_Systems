import sys
from pathlib import Path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

from VIGIA_Core.repository.user_repository import resolve_database_dsn
import psycopg2

conn = psycopg2.connect(resolve_database_dsn())
with conn.cursor() as cur:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'camara_credencial';")
    cols = [r[0] for r in cur.fetchall()]
    print("COLUMNS in camara_credencial:", cols)
    cur.execute("SELECT * FROM camara_credencial WHERE revocado_en IS NULL;")
    rows = cur.fetchall()
    print("ACTIVE CREDENTIALS:")
    for r in rows:
        print(" ", r)
conn.close()
