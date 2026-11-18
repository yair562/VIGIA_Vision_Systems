import psycopg2, os
from dotenv import load_dotenv
load_dotenv('C:/GEST.PROY.TI/Software/.env')

conn = psycopg2.connect(
    host=os.getenv('POSTGRES_HOST', '127.0.0.1'),
    port=int(os.getenv('POSTGRES_PORT', 5434)),
    dbname=os.getenv('POSTGRES_DB', 'vigia_db'),
    user=os.getenv('POSTGRES_USER', 'vigia_user'),
    password=os.getenv('POSTGRES_PASSWORD', '')
)
cur = conn.cursor()
cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'vehiculo' ORDER BY ordinal_position")
print("Columns in vehiculo:")
for r in cur.fetchall():
    print(" ", r)

cur.execute("SELECT COUNT(*) FROM vehiculo")
print("Rows in vehiculo:", cur.fetchone()[0])

cur.execute("SELECT installed_rank, version, description, type, script, installed_on, success FROM schema_version ORDER BY installed_rank")
print("Installed migrations in schema_version:")
for r in cur.fetchall():
    print(" ", r)
