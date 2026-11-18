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
cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'schema_version'")
print("Columns in schema_version:")
for r in cur.fetchall():
    print(" ", r)

cur.execute("SELECT * FROM schema_version")
print("Rows in schema_version:")
for r in cur.fetchall():
    print(" ", r)
