"""
tests.unit.test_detection_repository
=====================================
Pruebas unitarias para DetectionInsertDTO, map_tipo_vehiculo_ddl_v1
y PsycopgDetectionRepository (Fase 2D).

Ejecutables sin base de datos, sin psycopg2 instalado y sin hardware.
Todo acceso a la BD se realiza mediante dobles de prueba (mocks).

Cobertura:
  - PU-DR-01 a PU-DR-04: Instanciacion valida de DetectionInsertDTO.
  - PU-DR-05 a PU-DR-14: Rechazo de invariantes de DetectionInsertDTO.
  - PU-DR-15 a PU-DR-17: Helper map_tipo_vehiculo_ddl_v1.
  - PU-DR-18 a PU-DR-20: PsycopgDetectionRepository con psycopg2 simulado.
  - PU-DR-21:             IDetectionRepository es implementable con mock.
"""

import sys
import unittest
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

# Asegurar rutas en sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from VIGIA_Core.repository.detection_repository import (
    DatabaseConnectionError,
    DatabasePersistenceError,
    DetectionInsertDTO,
    IDetectionRepository,
    PsycopgDetectionRepository,
    map_tipo_vehiculo_ddl_v1,
)


# ==============================================================================
# Datos de prueba compartidos
# ==============================================================================

_VALID_AREA_ID = uuid4()
_TS_UTC = datetime(2026, 10, 28, 6, 0, 0, tzinfo=timezone.utc)
_VALID_DSN = "host=localhost dbname=vigia user=vigia password=test"


class TestDetectionInsertDTO(unittest.TestCase):
    """Pruebas unitarias para DetectionInsertDTO."""

    # --------------------------------------------------------------------------
    # Instanciacion valida
    # --------------------------------------------------------------------------

    def test_pu_dr_01_minimal_valid_dto(self):
        """PU-DR-01: DTO minimo valido solo con id_area_vision."""
        dto = DetectionInsertDTO(id_area_vision=_VALID_AREA_ID)
        self.assertEqual(dto.id_area_vision, _VALID_AREA_ID)
        self.assertIsNone(dto.placa_detectada)
        self.assertIsNone(dto.confianza_placa)
        self.assertIsNone(dto.confianza_vehiculo)
        self.assertIsNone(dto.tipo_vehiculo_pred)
        self.assertIsNone(dto.ruta_evidencia_foto)
        self.assertIsNone(dto.fecha_hora)

    def test_pu_dr_02_full_valid_dto(self):
        """PU-DR-02: DTO completo con todos los campos validos."""
        dto = DetectionInsertDTO(
            id_area_vision=_VALID_AREA_ID,
            placa_detectada="ABC1234",
            confianza_placa=0.88,
            confianza_vehiculo=0.95,
            tipo_vehiculo_pred="AUTOMOVIL",
            ruta_evidencia_foto="evidencias/2026/10/28/cam1_001.jpg",
            fecha_hora=_TS_UTC,
        )
        self.assertEqual(dto.placa_detectada, "ABC1234")
        self.assertEqual(dto.confianza_placa, 0.88)
        self.assertEqual(dto.confianza_vehiculo, 0.95)
        self.assertEqual(dto.tipo_vehiculo_pred, "AUTOMOVIL")
        self.assertEqual(dto.ruta_evidencia_foto, "evidencias/2026/10/28/cam1_001.jpg")
        self.assertEqual(dto.fecha_hora, _TS_UTC)

    def test_pu_dr_03_boundary_confidence_values(self):
        """PU-DR-03: Valores limite exactos 0.0 y 1.0 de confianza son permitidos."""
        dto_min = DetectionInsertDTO(
            id_area_vision=_VALID_AREA_ID,
            confianza_vehiculo=0.0,
        )
        self.assertEqual(dto_min.confianza_vehiculo, 0.0)

        dto_max = DetectionInsertDTO(
            id_area_vision=_VALID_AREA_ID,
            placa_detectada="XYZ999",
            confianza_placa=1.0,
            confianza_vehiculo=1.0,
        )
        self.assertEqual(dto_max.confianza_placa, 1.0)
        self.assertEqual(dto_max.confianza_vehiculo, 1.0)

    def test_pu_dr_04_all_allowed_tipos_vehiculo(self):
        """PU-DR-04: Todos los valores permitidos por el DDL V1 son aceptados."""
        for tipo in ("AUTOMOVIL", "CAMIONETA", "CAMION", "MOTOCICLETA", "OTRO"):
            dto = DetectionInsertDTO(
                id_area_vision=_VALID_AREA_ID,
                tipo_vehiculo_pred=tipo,
            )
            self.assertEqual(dto.tipo_vehiculo_pred, tipo)

    # --------------------------------------------------------------------------
    # Invariantes rechazadas
    # --------------------------------------------------------------------------

    def test_pu_dr_05_empty_plate_rejected(self):
        """PU-DR-05: Rechazo de placa_detectada cadena vacia."""
        with self.assertRaises(ValueError) as ctx:
            DetectionInsertDTO(id_area_vision=_VALID_AREA_ID, placa_detectada="")
        self.assertIn("vacia", str(ctx.exception))

    def test_pu_dr_06_lowercase_plate_rejected(self):
        """PU-DR-06: Rechazo de placa_detectada en minusculas."""
        with self.assertRaises(ValueError) as ctx:
            DetectionInsertDTO(id_area_vision=_VALID_AREA_ID, placa_detectada="abc1234")
        self.assertIn("mayusculas", str(ctx.exception))

    def test_pu_dr_07_plate_with_space_rejected(self):
        """PU-DR-07: Rechazo de placa_detectada con espacio interior."""
        with self.assertRaises(ValueError) as ctx:
            DetectionInsertDTO(id_area_vision=_VALID_AREA_ID, placa_detectada="AB CD12")
        self.assertIn("espacios", str(ctx.exception))

    def test_pu_dr_08_plate_with_hyphen_rejected(self):
        """PU-DR-08: Rechazo de placa_detectada con guion."""
        with self.assertRaises(ValueError) as ctx:
            DetectionInsertDTO(id_area_vision=_VALID_AREA_ID, placa_detectada="ABC-1234")
        self.assertIn("guiones", str(ctx.exception))

    def test_pu_dr_09_negative_vehicle_confidence_rejected(self):
        """PU-DR-09: Rechazo de confianza_vehiculo menor a 0.0."""
        with self.assertRaises(ValueError) as ctx:
            DetectionInsertDTO(id_area_vision=_VALID_AREA_ID, confianza_vehiculo=-0.01)
        self.assertIn("confianza_vehiculo=-0.01 fuera del rango", str(ctx.exception))

    def test_pu_dr_10_plate_confidence_above_one_rejected(self):
        """PU-DR-10: Rechazo de confianza_placa mayor a 1.0."""
        with self.assertRaises(ValueError) as ctx:
            DetectionInsertDTO(
                id_area_vision=_VALID_AREA_ID,
                placa_detectada="ABC1234",
                confianza_placa=1.001,
            )
        self.assertIn("confianza_placa=1.001 fuera del rango", str(ctx.exception))

    def test_pu_dr_11_autobus_tipo_rejected_directly(self):
        """PU-DR-11: AUTOBUS no es un valor DDL V1 valido; debe rechazarse en el DTO."""
        with self.assertRaises(ValueError) as ctx:
            DetectionInsertDTO(
                id_area_vision=_VALID_AREA_ID,
                tipo_vehiculo_pred="AUTOBUS",
            )
        self.assertIn("AUTOBUS", str(ctx.exception))
        self.assertIn("map_tipo_vehiculo_ddl_v1", str(ctx.exception))

    def test_pu_dr_12_unknown_tipo_rejected(self):
        """PU-DR-12: Tipo de vehiculo desconocido rechazado."""
        with self.assertRaises(ValueError):
            DetectionInsertDTO(
                id_area_vision=_VALID_AREA_ID,
                tipo_vehiculo_pred="BICICLETA",
            )

    def test_pu_dr_13_empty_evidence_path_rejected(self):
        """PU-DR-13: Rechazo de ruta_evidencia_foto cadena vacia."""
        with self.assertRaises(ValueError) as ctx:
            DetectionInsertDTO(id_area_vision=_VALID_AREA_ID, ruta_evidencia_foto="")
        self.assertIn("vacia", str(ctx.exception))

    def test_pu_dr_14_naive_datetime_rejected(self):
        """PU-DR-14: Rechazo de fecha_hora sin timezone (naive datetime)."""
        naive_dt = datetime(2026, 10, 28, 6, 0, 0)  # Sin tzinfo
        with self.assertRaises(ValueError) as ctx:
            DetectionInsertDTO(id_area_vision=_VALID_AREA_ID, fecha_hora=naive_dt)
        self.assertIn("timezone", str(ctx.exception))

    def test_pu_dr_immutability(self):
        """DTO es inmutable (frozen dataclass)."""
        dto = DetectionInsertDTO(id_area_vision=_VALID_AREA_ID)
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            dto.placa_detectada = "XYZ999"


class TestMapTipoVehiculo(unittest.TestCase):
    """Pruebas unitarias para el helper map_tipo_vehiculo_ddl_v1."""

    def test_pu_dr_15_autobus_maps_to_otro(self):
        """PU-DR-15: 'AUTOBUS' se mapea a 'OTRO' para compatibilidad DDL V1."""
        self.assertEqual(map_tipo_vehiculo_ddl_v1("AUTOBUS"), "OTRO")

    def test_pu_dr_16_ddl_compatible_values_pass_through(self):
        """PU-DR-16: Valores ya compatibles con el DDL V1 se retornan sin modificar."""
        for tipo in ("AUTOMOVIL", "CAMIONETA", "CAMION", "MOTOCICLETA", "OTRO"):
            self.assertEqual(map_tipo_vehiculo_ddl_v1(tipo), tipo)

    def test_pu_dr_17_none_returns_none(self):
        """PU-DR-17: None se retorna como None (sin vehiculo clasificado)."""
        self.assertIsNone(map_tipo_vehiculo_ddl_v1(None))


class TestPsycopgDetectionRepository(unittest.TestCase):
    """
    Pruebas unitarias para PsycopgDetectionRepository con psycopg2 simulado.
    No requieren base de datos real ni psycopg2 instalado.
    """

    def _make_repo_with_mock_psycopg2(self, mock_conn=None):
        """Crea un repositorio con psycopg2 completamente simulado."""
        mock_psycopg2 = MagicMock()

        if mock_conn is None:
            # Conexion nominal: RETURNING retorna un UUID
            returned_id = uuid4()
            mock_cursor = MagicMock()
            mock_cursor.__enter__ = lambda s: s
            mock_cursor.__exit__ = MagicMock(return_value=False)
            mock_cursor.fetchone.return_value = (str(returned_id),)

            mock_conn = MagicMock()
            mock_conn.__enter__ = lambda s: s
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_conn.cursor.return_value = mock_cursor
        else:
            returned_id = None  # El llamador controla el mock

        mock_psycopg2.connect.return_value = mock_conn

        # Parchear la importacion de psycopg2 dentro del modulo
        with patch.dict("sys.modules", {"psycopg2": mock_psycopg2}):
            repo = PsycopgDetectionRepository(dsn=_VALID_DSN)

        # Inyectar el mock directamente (importacion ya realizada)
        repo._psycopg2 = mock_psycopg2
        return repo, mock_psycopg2, mock_conn, returned_id

    def test_pu_dr_18_persist_detection_nominal(self):
        """PU-DR-18: persist_detection retorna el UUID de la fila insertada."""
        returned_id = uuid4()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = lambda s: s
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.return_value = (str(returned_id),)

        mock_conn = MagicMock()
        mock_conn.__enter__ = lambda s: s
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor

        mock_psycopg2 = MagicMock()
        mock_psycopg2.connect.return_value = mock_conn

        with patch.dict("sys.modules", {"psycopg2": mock_psycopg2}):
            repo = PsycopgDetectionRepository(dsn=_VALID_DSN)
        repo._psycopg2 = mock_psycopg2

        dto = DetectionInsertDTO(
            id_area_vision=_VALID_AREA_ID,
            confianza_vehiculo=0.90,
            tipo_vehiculo_pred="CAMIONETA",
            fecha_hora=_TS_UTC,
        )
        result_id = repo.persist_detection(dto)

        self.assertIsInstance(result_id, UUID)
        self.assertEqual(result_id, returned_id)
        mock_cursor.execute.assert_called_once()

    def test_pu_dr_19_connection_error_raises_database_connection_error(self):
        """PU-DR-19: Fallo de conexion lanza DatabaseConnectionError."""
        mock_psycopg2 = MagicMock()
        mock_psycopg2.OperationalError = ConnectionError
        mock_psycopg2.connect.side_effect = ConnectionError("Connection refused")

        with patch.dict("sys.modules", {"psycopg2": mock_psycopg2}):
            repo = PsycopgDetectionRepository(dsn=_VALID_DSN)
        repo._psycopg2 = mock_psycopg2

        dto = DetectionInsertDTO(id_area_vision=_VALID_AREA_ID)
        with self.assertRaises(DatabaseConnectionError):
            repo.persist_detection(dto)

    def test_pu_dr_20_sql_error_raises_database_persistence_error(self):
        """PU-DR-20: Violacion de CHECK u otro error SQL lanza DatabasePersistenceError."""
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = lambda s: s
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.execute.side_effect = Exception("CHECK constraint violation: ck_deteccion_placa")

        mock_conn = MagicMock()
        mock_conn.__enter__ = lambda s: s
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor

        mock_psycopg2 = MagicMock()
        mock_psycopg2.OperationalError = type("OperationalError", (Exception,), {})
        mock_psycopg2.connect.return_value = mock_conn

        with patch.dict("sys.modules", {"psycopg2": mock_psycopg2}):
            repo = PsycopgDetectionRepository(dsn=_VALID_DSN)
        repo._psycopg2 = mock_psycopg2

        dto = DetectionInsertDTO(id_area_vision=_VALID_AREA_ID)
        with self.assertRaises(DatabasePersistenceError) as ctx:
            repo.persist_detection(dto)
        self.assertIn("ck_deteccion_placa", str(ctx.exception))

    def test_pu_dr_21_concrete_class_implements_interface(self):
        """PU-DR-21: Cualquier clase con persist_detection satisface IDetectionRepository."""

        class StubRepo:
            """Doble de prueba minimo que implementa IDetectionRepository."""
            def persist_detection(self, data: DetectionInsertDTO) -> UUID:
                return uuid4()

        stub = StubRepo()
        # Protocol @runtime_checkable: isinstance verifica que el metodo exista
        self.assertTrue(isinstance(stub, IDetectionRepository))

        # Verificar que el stub devuelve UUID correctamente
        dto = DetectionInsertDTO(id_area_vision=_VALID_AREA_ID)
        result = stub.persist_detection(dto)
        self.assertIsInstance(result, UUID)

    def test_pu_dr_22_psycopg2_unavailable_raises_on_instantiation(self):
        """PU-DR-22: Si psycopg2 no esta instalado, la instanciacion lanza DatabaseConnectionError."""
        with patch.dict("sys.modules", {"psycopg2": None}):
            with self.assertRaises(DatabaseConnectionError):
                PsycopgDetectionRepository(dsn=_VALID_DSN)

    def test_pu_dr_23_autobus_maps_before_dto_creation(self):
        """PU-DR-23: El flujo correcto usa map_tipo_vehiculo_ddl_v1 antes de crear el DTO."""
        tipo_ia = "AUTOBUS"
        tipo_ddl = map_tipo_vehiculo_ddl_v1(tipo_ia)
        self.assertEqual(tipo_ddl, "OTRO")

        # El DTO con tipo_ddl='OTRO' debe instanciarse sin error
        dto = DetectionInsertDTO(
            id_area_vision=_VALID_AREA_ID,
            tipo_vehiculo_pred=tipo_ddl,
        )
        self.assertEqual(dto.tipo_vehiculo_pred, "OTRO")


class TestDetectionInsertDTOEdgeCases(unittest.TestCase):
    """Casos limite adicionales para DetectionInsertDTO."""

    def test_plate_with_leading_space_rejected(self):
        """Placa con espacio inicial falla la validacion upper().strip()."""
        with self.assertRaises(ValueError):
            DetectionInsertDTO(id_area_vision=_VALID_AREA_ID, placa_detectada=" ABC1234")

    def test_evidence_path_with_trailing_space_rejected(self):
        """Ruta de evidencia con espacio final rechazada."""
        with self.assertRaises(ValueError):
            DetectionInsertDTO(
                id_area_vision=_VALID_AREA_ID,
                ruta_evidencia_foto="evidencias/foto.jpg ",
            )

    def test_vehicle_confidence_exactly_zero(self):
        """Confianza de vehiculo exactamente 0.0 es valida."""
        dto = DetectionInsertDTO(id_area_vision=_VALID_AREA_ID, confianza_vehiculo=0.0)
        self.assertEqual(dto.confianza_vehiculo, 0.0)

    def test_vehicle_confidence_exactly_one(self):
        """Confianza de vehiculo exactamente 1.0 es valida."""
        dto = DetectionInsertDTO(id_area_vision=_VALID_AREA_ID, confianza_vehiculo=1.0)
        self.assertEqual(dto.confianza_vehiculo, 1.0)

    def test_placa_none_with_confianza_placa_allowed(self):
        """placa_detectada=None con confianza_placa no es bloqueado por el DTO (OCR sin placa es posible)."""
        # El DDL permite confianza_placa sin placa_detectada (son columnas independientes)
        dto = DetectionInsertDTO(
            id_area_vision=_VALID_AREA_ID,
            confianza_placa=0.30,  # Baja confianza: no hay placa
        )
        self.assertEqual(dto.confianza_placa, 0.30)
        self.assertIsNone(dto.placa_detectada)


if __name__ == "__main__":
    unittest.main()
