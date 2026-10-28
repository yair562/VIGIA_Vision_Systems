"""
VIGIA_Core.repository.detection_repository
==========================================
Contrato de persistencia relacional de detecciones para VIGÍA Vision Systems V1.

Implementa:
  - ``DetectionInsertDTO``: DTO inmutable que mapea estrictamente contra las
    columnas y restricciones CHECK del DDL ``V001__baseline_schema.sql``.
  - ``IDetectionRepository``: Interfaz (Protocol) de persistencia de detecciones.
  - ``PsycopgDetectionRepository``: Implementación concreta con ``psycopg2``.
  - ``DatabaseConnectionError``, ``DatabasePersistenceError``: Taxonomía de errores
    definida en DOC-04, Sección 7.

Restricciones de diseño (DOC-04, Sección 6):
  - Este repositorio es responsable **exclusivamente** de la persistencia de datos
    relacionales en PostgreSQL (tabla ``deteccion``).
  - No realiza almacenamiento de archivos físicos en disco.
  - No toma decisiones de acceso ni evalúa reglas de autorización.
  - El tipo de vehículo predicho debe ser compatible con el CHECK del DDL V1:
    ``('AUTOMOVIL', 'CAMIONETA', 'CAMION', 'MOTOCICLETA', 'OTRO')``.
    'AUTOBUS' debe mapearse a 'OTRO' en la capa de persistencia hasta que
    se apruebe la migración DDL V004 (decisión pendiente de aprobación colegiada).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Protocol, runtime_checkable
from uuid import UUID

logger = logging.getLogger(__name__)


# ==============================================================================
# Taxonomia de errores tecnicos (DOC-04, Seccion 7)
# ==============================================================================

class DatabaseConnectionError(Exception):
    """
    Fallo de conexion a PostgreSQL (red caida, credenciales invalidas, timeout).
    Categorizacion: CRITICO - bloquea arranque o pausa el bucle de operacion.
    """


class DatabasePersistenceError(Exception):
    """
    Fallo de insercion SQL (violacion de CHECK, FK invalida, timeout de transaccion).
    Categorizacion: OPERATIVO - registra error critico en log; no detiene el servicio.
    """


# ==============================================================================
# Constantes DDL V1
# ==============================================================================

#: Valores permitidos por ``ck_deteccion_tipo_vehiculo`` en V001__baseline_schema.sql
_DDL_V1_TIPOS_VEHICULO = frozenset({
    "AUTOMOVIL",
    "CAMIONETA",
    "CAMION",
    "MOTOCICLETA",
    "OTRO",
})

#: Mapeo de valores Python no soportados por el DDL V1 a valores seguros
_TIPO_VEHICULO_DDL_SAFE: dict = {
    "AUTOBUS": "OTRO",
}


# ==============================================================================
# DTO de entrada (DOC-04, Seccion 6.1)
# ==============================================================================

@dataclass(frozen=True)
class DetectionInsertDTO:
    """
    Datos estructurados requeridos para insertar en la tabla relacional ``deteccion``.
    Mapea de forma estricta contra las columnas y restricciones de V001__baseline_schema.sql.

    Atributos
    ---------
    id_area_vision : UUID
        Referencia a ``area_vision.id_area_vision`` (NOT NULL, FK con ON DELETE RESTRICT).
    fecha_hora : Optional[datetime]
        Marca de tiempo de la deteccion (TIMESTAMPTZ). Debe incluir zona horaria.
        Si se omite (None), la BD aplica ``CURRENT_TIMESTAMP`` por omision.
    placa_detectada : Optional[str]
        Cadena de matricula. Debe estar en mayusculas, sin espacios ni guiones y no
        puede ser cadena vacia. Se valida contra ``ck_deteccion_placa``.
        Pasar ``None`` si no se detecto matricula.
    confianza_placa : Optional[float]
        Confianza OCR en ``[0.0, 1.0]``. ``None`` si ``placa_detectada`` es ``None``.
    confianza_vehiculo : Optional[float]
        Confianza de deteccion del vehiculo en ``[0.0, 1.0]``.
    tipo_vehiculo_pred : Optional[str]
        Tipo predicho. Debe ser uno de los valores del CHECK DDL V1.
        Usar ``None`` si el clasificador no emitio tipo.
    ruta_evidencia_foto : Optional[str]
        Ruta relativa al archivo de evidencia. No puede ser cadena vacia ni tener
        espacios iniciales/finales (``ck_deteccion_evidencia``).
        Pasar ``None`` si no se guardo evidencia.
    """

    id_area_vision: UUID
    placa_detectada: Optional[str] = None
    confianza_placa: Optional[float] = None
    confianza_vehiculo: Optional[float] = None
    tipo_vehiculo_pred: Optional[str] = None
    ruta_evidencia_foto: Optional[str] = None
    fecha_hora: Optional[datetime] = None  # None -> BD aplica CURRENT_TIMESTAMP

    def __post_init__(self) -> None:
        """Valida las restricciones del DTO que tambien estan presentes en el DDL."""
        # Placa: si presente, debe ser mayusculas, sin espacios/guiones y no vacia
        if self.placa_detectada is not None:
            placa = self.placa_detectada
            if placa == "":
                raise ValueError("placa_detectada no puede ser cadena vacia.")
            if placa != placa.upper().strip():
                raise ValueError(
                    f"placa_detectada='{placa}' debe estar en mayusculas y sin espacios extremos."
                )
            if " " in placa or "-" in placa:
                raise ValueError(
                    f"placa_detectada='{placa}' no puede contener espacios ni guiones."
                )

        # Confianzas en [0.0, 1.0]
        for label, value in (
            ("confianza_placa", self.confianza_placa),
            ("confianza_vehiculo", self.confianza_vehiculo),
        ):
            if value is not None and not (0.0 <= value <= 1.0):
                raise ValueError(
                    f"{label}={value} fuera del rango permitido [0.0, 1.0]."
                )

        # tipo_vehiculo_pred debe ser un valor DDL V1 seguro (si no es None)
        if self.tipo_vehiculo_pred is not None:
            tipo = self.tipo_vehiculo_pred
            if tipo not in _DDL_V1_TIPOS_VEHICULO:
                raise ValueError(
                    f"tipo_vehiculo_pred='{tipo}' no es un valor permitido por el DDL V1. "
                    f"Valores aceptados: {sorted(_DDL_V1_TIPOS_VEHICULO)}. "
                    f"Use map_tipo_vehiculo_ddl_v1() para convertir 'AUTOBUS' a 'OTRO'."
                )

        # Evidencia: si presente, no puede ser cadena vacia ni tener espacios extremos
        if self.ruta_evidencia_foto is not None:
            ruta = self.ruta_evidencia_foto
            if ruta == "" or ruta != ruta.strip():
                raise ValueError(
                    f"ruta_evidencia_foto='{ruta}' no puede ser vacia ni tener espacios extremos."
                )

        # fecha_hora: si presente, debe tener zona horaria
        if self.fecha_hora is not None and self.fecha_hora.tzinfo is None:
            raise ValueError(
                "fecha_hora debe incluir informacion de zona horaria (timezone-aware)."
            )


# ==============================================================================
# Helpers de mapeo (DOC-04, Seccion 5.2)
# ==============================================================================

def map_tipo_vehiculo_ddl_v1(tipo: Optional[str]) -> Optional[str]:
    """
    Convierte un tipo de vehiculo predicho por el clasificador de IA al valor
    compatible con el CHECK ``ck_deteccion_tipo_vehiculo`` del DDL V1.

    'AUTOBUS' -> 'OTRO'  (mapeo pendiente de aprobacion de migracion DDL V004).
    Cualquier valor ya compatible se retorna sin modificar.
    ``None`` se retorna como ``None``.
    """
    if tipo is None:
        return None
    return _TIPO_VEHICULO_DDL_SAFE.get(tipo, tipo)


# ==============================================================================
# Interfaz del repositorio (Protocol - DOC-04, Seccion 6.1)
# ==============================================================================

@runtime_checkable
class IDetectionRepository(Protocol):
    """
    Interfaz de repositorio de persistencia de detecciones.

    Implementada por cualquier clase que exponga ``persist_detection``.
    Compatible con inyeccion de dependencias y dobles de prueba (mocks).
    """

    def persist_detection(self, data: DetectionInsertDTO) -> UUID:
        """
        Inserta un registro en la tabla relacional ``deteccion``.

        Parametros
        ----------
        data : DetectionInsertDTO
            DTO inmutable con los datos de la deteccion, ya validados.

        Retorna
        -------
        UUID
            El ``id_deteccion`` generado por PostgreSQL (``gen_random_uuid()``).

        Lanza
        -----
        DatabaseConnectionError
            Ante fallos de conexion a PostgreSQL (red, credenciales, timeout).
        DatabasePersistenceError
            Ante violaciones de restricciones CHECK/FK o fallos transaccionales.
        """
        ...  # pragma: no cover


# ==============================================================================
# Implementacion concreta con psycopg2 (DOC-04, Seccion 6.1)
# ==============================================================================

_INSERT_SQL = """
    INSERT INTO deteccion (
        id_area_vision,
        fecha_hora,
        placa_detectada,
        confianza_placa,
        confianza_vehiculo,
        tipo_vehiculo_pred,
        ruta_evidencia_foto
    ) VALUES (
        %(id_area_vision)s,
        %(fecha_hora)s,
        %(placa_detectada)s,
        %(confianza_placa)s,
        %(confianza_vehiculo)s,
        %(tipo_vehiculo_pred)s,
        %(ruta_evidencia_foto)s
    )
    RETURNING id_deteccion;
"""


class PsycopgDetectionRepository:
    """
    Implementacion concreta de ``IDetectionRepository`` usando ``psycopg2``.

    El driver ``psycopg2`` se importa de forma perezosa en ``__init__`` para
    que el modulo sea importable y testeable sin necesidad de que el paquete
    este instalado. Si el driver no esta disponible, se lanza
    ``DatabaseConnectionError`` en el momento de instanciacion.

    Uso tipico en produccion::

        import os
        from uuid import UUID
        from VIGIA_Core.repository.detection_repository import (
            PsycopgDetectionRepository,
            DetectionInsertDTO,
            map_tipo_vehiculo_ddl_v1,
        )

        repo = PsycopgDetectionRepository(dsn=os.environ["DATABASE_URL"])
        dto = DetectionInsertDTO(
            id_area_vision=UUID("..."),
            confianza_vehiculo=0.87,
            tipo_vehiculo_pred=map_tipo_vehiculo_ddl_v1("AUTOBUS"),  # -> 'OTRO'
        )
        id_deteccion = repo.persist_detection(dto)

    Parametros del constructor
    --------------------------
    dsn : str
        Cadena de conexion DSN compatible con psycopg2 (libpq).
        Ejemplo: ``"host=localhost dbname=vigia user=vigia password=s3cr3t"``
        o URL: ``"postgresql://vigia:s3cr3t@localhost:5432/vigia"``.
    connect_timeout : int
        Segundos de espera antes de declarar fallo de conexion. Por omision: 5.
    """

    def __init__(self, dsn: str, connect_timeout: int = 5) -> None:
        self._dsn = dsn
        self._connect_timeout = connect_timeout
        # Importacion perezosa: falla en este punto si psycopg2 no esta instalado
        try:
            import psycopg2  # noqa: F401
            self._psycopg2 = psycopg2
        except ImportError as exc:
            raise DatabaseConnectionError(
                "psycopg2 no esta instalado. "
                "Instale 'psycopg2-binary' o 'psycopg2' antes de usar "
                "PsycopgDetectionRepository. "
                f"Error original: {exc}"
            ) from exc

    def _get_connection(self) -> Any:
        """Abre y retorna una conexion a PostgreSQL."""
        try:
            conn = self._psycopg2.connect(
                self._dsn,
                connect_timeout=self._connect_timeout,
            )
            return conn
        except self._psycopg2.OperationalError as exc:
            raise DatabaseConnectionError(
                f"No se pudo conectar a PostgreSQL: {exc}"
            ) from exc

    def persist_detection(self, data: DetectionInsertDTO) -> UUID:
        """
        Inserta un registro en la tabla ``deteccion`` de PostgreSQL.

        La insercion se realiza dentro de una transaccion explicita que hace
        COMMIT en caso de exito o ROLLBACK en caso de error de restriccion.

        La columna ``fecha_hora`` se envia como el valor del DTO si esta presente;
        de lo contrario, se genera ``datetime.now(timezone.utc)`` en Python antes
        del INSERT (la BD tambien aplica ``CURRENT_TIMESTAMP`` si se envia NULL,
        pero ser explicitos mejora la trazabilidad de logs).
        """
        # Preparar la marca de tiempo
        fecha_hora = data.fecha_hora or datetime.now(timezone.utc)

        params = {
            "id_area_vision": str(data.id_area_vision),
            "fecha_hora": fecha_hora,
            "placa_detectada": data.placa_detectada,
            "confianza_placa": data.confianza_placa,
            "confianza_vehiculo": data.confianza_vehiculo,
            "tipo_vehiculo_pred": data.tipo_vehiculo_pred,
            "ruta_evidencia_foto": data.ruta_evidencia_foto,
        }

        conn = None
        try:
            conn = self._get_connection()
            with conn:
                with conn.cursor() as cur:
                    cur.execute(_INSERT_SQL, params)
                    row = cur.fetchone()
                    if row is None:
                        raise DatabasePersistenceError(
                            "La insercion en 'deteccion' no retorno id_deteccion."
                        )
                    id_deteccion = UUID(str(row[0]))

            logger.info(
                "Deteccion persistida correctamente. id_deteccion=%s, area=%s",
                id_deteccion,
                data.id_area_vision,
            )
            return id_deteccion

        except DatabaseConnectionError:
            raise  # Re-propagar sin envolver
        except Exception as exc:
            # Captura violaciones de CHECK, FK, timeout SQL, etc.
            raise DatabasePersistenceError(
                f"Error al insertar en 'deteccion': {exc}"
            ) from exc
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
