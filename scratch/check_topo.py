import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

from VIGIA_Core.config.env_loader import get_setting
from VIGIA_Vision.config.psycopg_topology_repository import PsycopgTopologyConfigRepository
from VIGIA_Core.repository.user_repository import resolve_database_dsn

dsn = resolve_database_dsn()
repo = PsycopgTopologyConfigRepository(dsn=dsn)
cameras = repo.get_cameras()
areas = repo.get_areas()
print(f"Total cameras configured: {len(cameras)}")
for c in cameras:
    print(f"  Camera: id={c.id_camara}, codigo={c.codigo}, activa={c.activa}, id_area={c.id_area_vision}")
print(f"Total areas configured: {len(areas)}")
for a in areas:
    print(f"  Area: id={a.id_area_vision}, codigo={a.codigo}, activa={a.activa}")
