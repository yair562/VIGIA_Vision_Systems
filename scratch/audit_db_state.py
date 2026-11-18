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
cur.execute('SELECT COUNT(*) FROM deteccion')
count_det = cur.fetchone()[0]

cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public' 
    ORDER BY table_name
""")
tables = [r[0] for r in cur.fetchall()]

cur.execute("""
    SELECT column_name 
    FROM information_schema.columns 
    WHERE table_name = 'deteccion' 
    ORDER BY ordinal_position
""")
cols_det = [r[0] for r in cur.fetchall()]

print(f"Total detecciones en BD: {count_det}")
print(f"Tablas en schema public: {tables}")
print(f"Columnas en deteccion: {cols_det}")
print(f"Existe tabla vehiculo: {'vehiculo' in tables}")
print(f"Existe columna color en deteccion: {'color_vehiculo_pred' in cols_det}")
print(f"Existe tabla seguimiento_vehicular: {'seguimiento_vehicular' in tables}")
print(f"Existe tabla historial_color_vehiculo: {'historial_color_vehiculo' in tables}")
print(f"Existe tabla matricula_candidata: {'matricula_candidata' in tables}")
