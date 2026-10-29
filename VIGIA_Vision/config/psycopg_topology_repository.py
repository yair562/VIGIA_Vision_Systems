"""
VIGIA_Vision.config.psycopg_topology_repository
===============================================
Adaptador PostgreSQL de solo lectura para ``ITopologyConfigRepository``.

Lee exclusivamente las columnas necesarias de las tablas ``camara`` y
``area_vision`` definidas en ``BD/migrations/V001__baseline_schema.sql`` y
construye los contratos inmutables ``CameraConfigDTO`` y ``AreaConfigDTO``.

Reglas de diseño:
- Cumple el protocolo ``ITopologyConfigRepository`` sin añadir validaciones
  paralelas que contradigan a ``TopologyValidator``.
- No ejecuta operaciones de escritura ni modifica la topología.
- No abre conexiones ni importa el driver en tiempo de importación del módulo.
- Cierra de forma garantizada cursores y conexiones en bloques ``finally``.
- Traduce los fallos de conexión o consulta a ``DatabaseConnectionError``
  preservando la excepción original (``from exc``) sin exponer credenciales.
"""

from __future__ import annotations

from typing import Any, Callable, List, Optional
from uuid import UUID

from VIGIA_Core.repository.detection_repository import DatabaseConnectionError
from VIGIA_Vision.config.topology_validator import (
    AreaConfigDTO,
    CameraConfigDTO,
    ITopologyConfigRepository,
)

_SELECT_CAMERAS_SQL = """
    SELECT
        id_camara,
        codigo,
        nombre,
        uri_stream,
        activa
    FROM camara
    ORDER BY codigo ASC;
"""

_SELECT_AREAS_SQL = """
    SELECT
        id_area_vision,
        id_camara,
        codigo,
        nombre,
        tipo_movimiento,
        x_min,
        y_min,
        x_max,
        y_max,
        activa
    FROM area_vision
    ORDER BY codigo ASC;
"""


class PsycopgTopologyConfigRepository(ITopologyConfigRepository):
    """
    Implementación concreta de ``ITopologyConfigRepository`` respaldada por
    PostgreSQL mediante ``psycopg2`` (o una fábrica de conexiones inyectable
    para pruebas unitarias).

    Parámetros
    ----------
    dsn : str
        Cadena de conexión DSN para PostgreSQL. No puede ser vacía.
    connect_timeout : int
        Tiempo máximo de espera de conexión en segundos (debe ser > 0).
    connection_factory : Optional[Callable[..., Any]]
        Fábrica opcional ``(dsn, connect_timeout=...) -> connection`` para
        pruebas unitarias sin requerir una instancia PostgreSQL activa.
    """

    def __init__(
        self,
        dsn: str,
        connect_timeout: int = 5,
        connection_factory: Optional[Callable[..., Any]] = None,
    ) -> None:
        if not isinstance(dsn, str) or not dsn.strip():
            raise ValueError("dsn debe ser una cadena no vacía.")
        if isinstance(connect_timeout, bool) or not isinstance(connect_timeout, int) or connect_timeout <= 0:
            raise ValueError("connect_timeout debe ser un entero positivo.")

        self._dsn = dsn
        self._connect_timeout = connect_timeout
        self._connection_factory = connection_factory
        self._psycopg2: Any = None

        if self._connection_factory is None:
            try:
                import psycopg2  # noqa: F401
                self._psycopg2 = psycopg2
            except ImportError as exc:
                raise DatabaseConnectionError(
                    "psycopg2 no está instalado; no se puede instanciar "
                    "PsycopgTopologyConfigRepository sin connection_factory."
                ) from exc

    def _open_connection(self) -> Any:
        """Abre una conexión nueva a PostgreSQL sin exponer credenciales en errores."""
        try:
            if self._connection_factory is not None:
                return self._connection_factory(
                    self._dsn,
                    connect_timeout=self._connect_timeout,
                )
            return self._psycopg2.connect(
                self._dsn,
                connect_timeout=self._connect_timeout,
            )
        except DatabaseConnectionError:
            raise
        except Exception as exc:
            raise DatabaseConnectionError(
                f"Fallo al abrir conexión con PostgreSQL para lectura de topología: {type(exc).__name__}"
            ) from exc

    def get_cameras(self) -> List[CameraConfigDTO]:
        """
        Consulta todas las cámaras registradas en la tabla ``camara`` y retorna
        instancias de ``CameraConfigDTO``.
        """
        conn = None
        cur = None
        try:
            conn = self._open_connection()
            cur = conn.cursor()
            cur.execute(_SELECT_CAMERAS_SQL)
            rows = cur.fetchall() or []
            cameras: List[CameraConfigDTO] = []
            for row in rows:
                id_camara, codigo, nombre, uri_stream, activa = row
                cameras.append(
                    CameraConfigDTO(
                        id_camara=id_camara if isinstance(id_camara, UUID) else UUID(str(id_camara)),
                        codigo=str(codigo),
                        nombre=str(nombre),
                        uri_stream=str(uri_stream),
                        activa=bool(activa),
                    )
                )
            return cameras
        except DatabaseConnectionError:
            raise
        except Exception as exc:
            raise DatabaseConnectionError(
                f"Error al consultar la tabla 'camara' en PostgreSQL: {exc}"
            ) from exc
        finally:
            if cur is not None:
                try:
                    cur.close()
                except Exception:
                    pass
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def get_areas(self) -> List[AreaConfigDTO]:
        """
        Consulta todas las áreas de visión registradas en la tabla ``area_vision``
        y retorna instancias de ``AreaConfigDTO``.
        """
        conn = None
        cur = None
        try:
            conn = self._open_connection()
            cur = conn.cursor()
            cur.execute(_SELECT_AREAS_SQL)
            rows = cur.fetchall() or []
            areas: List[AreaConfigDTO] = []
            for row in rows:
                (
                    id_area_vision,
                    id_camara,
                    codigo,
                    nombre,
                    tipo_movimiento,
                    x_min,
                    y_min,
                    x_max,
                    y_max,
                    activa,
                ) = row
                areas.append(
                    AreaConfigDTO(
                        id_area_vision=(
                            id_area_vision
                            if isinstance(id_area_vision, UUID)
                            else UUID(str(id_area_vision))
                        ),
                        id_camara=(
                            id_camara
                            if isinstance(id_camara, UUID)
                            else UUID(str(id_camara))
                        ),
                        codigo=str(codigo),
                        nombre=str(nombre),
                        tipo_movimiento=str(tipo_movimiento),
                        x_min=float(x_min),
                        y_min=float(y_min),
                        x_max=float(x_max),
                        y_max=float(y_max),
                        activa=bool(activa),
                    )
                )
            return areas
        except DatabaseConnectionError:
            raise
        except Exception as exc:
            raise DatabaseConnectionError(
                f"Error al consultar la tabla 'area_vision' en PostgreSQL: {exc}"
            ) from exc
        finally:
            if cur is not None:
                try:
                    cur.close()
                except Exception:
                    pass
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def __repr__(self) -> str:
        return f"PsycopgTopologyConfigRepository(connect_timeout={self._connect_timeout})"
