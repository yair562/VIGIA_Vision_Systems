"""
tests.unit.test_topology_validator
==================================
Pruebas unitarias para TopologyValidator (Fase 2C).
Verifica deterministamente las 8 reglas de DOC-03 y el bloqueo fail-fast de captura.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

# Asegurar rutas en sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from VIGIA_Vision.capture.sources import IFrameCaptureSource
from VIGIA_Vision.config.topology_validator import (
    AreaConfigDTO,
    CameraConfigDTO,
    ITopologyConfigRepository,
    OperationalTopologyDTO,
    TopologyErrorCode,
    TopologyValidationError,
    TopologyValidationResult,
    TopologyValidator,
)
from VIGIA_Vision.runtime.coordinator import IVehicleDetector, VisionEngineCoordinator


class TestTopologyValidator(unittest.TestCase):
    def setUp(self):
        # Generar IDs y datos válidos nominales por omisión
        self.id_cam_ent = uuid4()
        self.id_cam_sal = uuid4()
        self.id_area_ent = uuid4()
        self.id_area_sal = uuid4()

        self.valid_cam_entrada = CameraConfigDTO(
            id_camara=self.id_cam_ent,
            codigo="CAM-ENTRADA",
            nombre="Cámara Acceso Entrada",
            uri_stream="rtsp://192.168.1.101/stream",
            activa=True,
        )

        self.valid_cam_salida = CameraConfigDTO(
            id_camara=self.id_cam_sal,
            codigo="CAM-SALIDA",
            nombre="Cámara Acceso Salida",
            uri_stream="rtsp://192.168.1.102/stream",
            activa=True,
        )

        self.valid_area_entrada = AreaConfigDTO(
            id_area_vision=self.id_area_ent,
            id_camara=self.id_cam_ent,
            codigo="ROI-ENT",
            nombre="Área Vehicular Entrada",
            tipo_movimiento="ENTRADA",
            x_min=0.100,
            y_min=0.100,
            x_max=0.900,
            y_max=0.900,
            activa=True,
        )

        self.valid_area_salida = AreaConfigDTO(
            id_area_vision=self.id_area_sal,
            id_camara=self.id_cam_sal,
            codigo="ROI-SAL",
            nombre="Área Vehicular Salida",
            tipo_movimiento="SALIDA",
            x_min=0.100,
            y_min=0.100,
            x_max=0.900,
            y_max=0.900,
            activa=True,
        )

        self.validator = TopologyValidator()

    # --------------------------------------------------------------------------
    # Regla 1 a 8: Pruebas unitarias de las 8 reglas de DOC-03
    # --------------------------------------------------------------------------

    def test_nominal_valid_topology_success(self):
        """Topología nominal válida: 2 cámaras activas y 2 áreas con movimientos y ROIs correctas."""
        cams = [self.valid_cam_entrada, self.valid_cam_salida]
        areas = [self.valid_area_entrada, self.valid_area_salida]

        result = self.validator.validate(cameras=cams, areas=areas)

        self.assertTrue(result.is_valid)
        self.assertIsNone(result.error_code)
        self.assertIsNone(result.error_detail)
        self.assertIsInstance(result.topology, OperationalTopologyDTO)
        self.assertEqual(result.topology.cam_entrada.codigo, "CAM-ENTRADA")
        self.assertEqual(result.topology.cam_salida.codigo, "CAM-SALIDA")
        self.assertEqual(result.topology.area_entrada.tipo_movimiento, "ENTRADA")
        self.assertEqual(result.topology.area_salida.tipo_movimiento, "SALIDA")

    def test_rule_1_cam_entrada_missing(self):
        """Regla 1 (R1 - VAL-CAM-ENTRADA): Rechaza si falta CAM-ENTRADA."""
        cams = [self.valid_cam_salida]
        areas = [self.valid_area_entrada, self.valid_area_salida]

        result = self.validator.validate(cameras=cams, areas=areas)

        self.assertFalse(result.is_valid)
        self.assertEqual(result.error_code, TopologyErrorCode.ERR_CAM_ENTRADA_FALTANTE)
        self.assertIn("CAM-ENTRADA", result.error_detail)

    def test_rule_2_cam_salida_missing(self):
        """Regla 2 (R2 - VAL-CAM-SALIDA): Rechaza si falta CAM-SALIDA."""
        cams = [self.valid_cam_entrada]
        areas = [self.valid_area_entrada, self.valid_area_salida]

        result = self.validator.validate(cameras=cams, areas=areas)

        self.assertFalse(result.is_valid)
        self.assertEqual(result.error_code, TopologyErrorCode.ERR_CAM_SALIDA_FALTANTE)
        self.assertIn("CAM-SALIDA", result.error_detail)

    def test_rule_3_cam_entrada_inactive(self):
        """Regla 3 (R3 - VAL-CAM-INACTIVA): Rechaza si CAM-ENTRADA tiene activa=False."""
        cam_inactiva = CameraConfigDTO(
            id_camara=self.id_cam_ent,
            codigo="CAM-ENTRADA",
            nombre="Cámara Inactiva",
            uri_stream="rtsp://...",
            activa=False,
        )
        cams = [cam_inactiva, self.valid_cam_salida]
        areas = [self.valid_area_entrada, self.valid_area_salida]

        result = self.validator.validate(cameras=cams, areas=areas)

        self.assertFalse(result.is_valid)
        self.assertEqual(result.error_code, TopologyErrorCode.ERR_CAM_INACTIVA)
        self.assertIn("CAM-ENTRADA", result.error_detail)

    def test_rule_3_cam_salida_inactive(self):
        """Regla 3 (R3 - VAL-CAM-INACTIVA): Rechaza si CAM-SALIDA tiene activa=False."""
        cam_inactiva = CameraConfigDTO(
            id_camara=self.id_cam_sal,
            codigo="CAM-SALIDA",
            nombre="Cámara Salida Inactiva",
            uri_stream="rtsp://...",
            activa=False,
        )
        cams = [self.valid_cam_entrada, cam_inactiva]
        areas = [self.valid_area_entrada, self.valid_area_salida]

        result = self.validator.validate(cameras=cams, areas=areas)

        self.assertFalse(result.is_valid)
        self.assertEqual(result.error_code, TopologyErrorCode.ERR_CAM_INACTIVA)
        self.assertIn("CAM-SALIDA", result.error_detail)

    def test_rule_4_areas_total_insufficient(self):
        """Regla 4 (R4 - VAL-AREAS-TOTAL): Rechaza si hay menos de 2 áreas activas en el sistema."""
        cams = [self.valid_cam_entrada, self.valid_cam_salida]
        areas = [self.valid_area_entrada]  # Solo 1 área activa

        result = self.validator.validate(cameras=cams, areas=areas)

        self.assertFalse(result.is_valid)
        self.assertEqual(result.error_code, TopologyErrorCode.ERR_AREAS_TOTAL_INVALIDO)
        self.assertIn("1", result.error_detail)

    def test_rule_4_areas_total_excessive(self):
        """Regla 4 (R4 - VAL-AREAS-TOTAL): Rechaza si hay más de 2 áreas activas en el sistema."""
        tercera_area = AreaConfigDTO(
            id_area_vision=uuid4(),
            id_camara=self.id_cam_ent,
            codigo="ROI-EXTRA",
            nombre="Área Extra",
            tipo_movimiento="ENTRADA",
            x_min=0.2, y_min=0.2, x_max=0.8, y_max=0.8,
            activa=True,
        )
        cams = [self.valid_cam_entrada, self.valid_cam_salida]
        areas = [self.valid_area_entrada, self.valid_area_salida, tercera_area]

        result = self.validator.validate(cameras=cams, areas=areas)

        self.assertFalse(result.is_valid)
        self.assertEqual(result.error_code, TopologyErrorCode.ERR_AREAS_TOTAL_INVALIDO)
        self.assertIn("3", result.error_detail)

    def test_rule_5_association_imbalanced(self):
        """Regla 5 (R5 - VAL-ASOC-1A1): Rechaza si CAM-ENTRADA tiene 2 áreas y CAM-SALIDA tiene 0."""
        area_2_entrada = AreaConfigDTO(
            id_area_vision=uuid4(),
            id_camara=self.id_cam_ent,  # Mismo id_camara de entrada
            codigo="ROI-ENT-2",
            nombre="Segunda Área Entrada",
            tipo_movimiento="ENTRADA",
            x_min=0.2, y_min=0.2, x_max=0.8, y_max=0.8,
            activa=True,
        )
        cams = [self.valid_cam_entrada, self.valid_cam_salida]
        areas = [self.valid_area_entrada, area_2_entrada]

        result = self.validator.validate(cameras=cams, areas=areas)

        self.assertFalse(result.is_valid)
        self.assertEqual(result.error_code, TopologyErrorCode.ERR_ASOCIACION_AREA_CAMARA)

    def test_rule_6_inverted_movement_entrada(self):
        """Regla 6 (R6 - VAL-MOV-ENTRADA): Rechaza si el área de CAM-ENTRADA no es 'ENTRADA'."""
        area_mov_invalido = AreaConfigDTO(
            id_area_vision=self.id_area_ent,
            id_camara=self.id_cam_ent,
            codigo="ROI-ENT",
            nombre="Área con movimiento erróneo",
            tipo_movimiento="SALIDA",  # Debería ser ENTRADA
            x_min=0.1, y_min=0.1, x_max=0.9, y_max=0.9,
            activa=True,
        )
        cams = [self.valid_cam_entrada, self.valid_cam_salida]
        areas = [area_mov_invalido, self.valid_area_salida]

        result = self.validator.validate(cameras=cams, areas=areas)

        self.assertFalse(result.is_valid)
        self.assertEqual(result.error_code, TopologyErrorCode.ERR_MOVIMIENTO_INVERTIDO)
        self.assertIn("CAM-ENTRADA", result.error_detail)

    def test_rule_7_inverted_movement_salida(self):
        """Regla 7 (R7 - VAL-MOV-SALIDA): Rechaza si el área de CAM-SALIDA no es 'SALIDA'."""
        area_mov_invalido = AreaConfigDTO(
            id_area_vision=self.id_area_sal,
            id_camara=self.id_cam_sal,
            codigo="ROI-SAL",
            nombre="Área con movimiento erróneo",
            tipo_movimiento="ENTRADA",  # Debería ser SALIDA
            x_min=0.1, y_min=0.1, x_max=0.9, y_max=0.9,
            activa=True,
        )
        cams = [self.valid_cam_entrada, self.valid_cam_salida]
        areas = [self.valid_area_entrada, area_mov_invalido]

        result = self.validator.validate(cameras=cams, areas=areas)

        self.assertFalse(result.is_valid)
        self.assertEqual(result.error_code, TopologyErrorCode.ERR_MOVIMIENTO_INVERTIDO)
        self.assertIn("CAM-SALIDA", result.error_detail)

    def test_rule_8_roi_out_of_bounds_negative(self):
        """Regla 8 (R8 - VAL-ROI-GEOM): Rechaza coordenadas menores a 0.0."""
        area_negativa = AreaConfigDTO(
            id_area_vision=self.id_area_ent,
            id_camara=self.id_cam_ent,
            codigo="ROI-NEG",
            nombre="Área Coordenada Negativa",
            tipo_movimiento="ENTRADA",
            x_min=-0.05, y_min=0.1, x_max=0.9, y_max=0.9,
            activa=True,
        )
        cams = [self.valid_cam_entrada, self.valid_cam_salida]
        areas = [area_negativa, self.valid_area_salida]

        result = self.validator.validate(cameras=cams, areas=areas)

        self.assertFalse(result.is_valid)
        self.assertEqual(result.error_code, TopologyErrorCode.ERR_ROI_DEGENERADA)

    def test_rule_8_roi_inverted_coordinates(self):
        """Regla 8 (R8 - VAL-ROI-GEOM): Rechaza x_min >= x_max."""
        area_invertida = AreaConfigDTO(
            id_area_vision=self.id_area_ent,
            id_camara=self.id_cam_ent,
            codigo="ROI-INV",
            nombre="Área Invertida",
            tipo_movimiento="ENTRADA",
            x_min=0.8, y_min=0.1, x_max=0.2, y_max=0.9,
            activa=True,
        )
        cams = [self.valid_cam_entrada, self.valid_cam_salida]
        areas = [area_invertida, self.valid_area_salida]

        result = self.validator.validate(cameras=cams, areas=areas)

        self.assertFalse(result.is_valid)
        self.assertEqual(result.error_code, TopologyErrorCode.ERR_ROI_DEGENERADA)

    def test_rule_8_roi_degenerate_insignificant_area(self):
        """Regla 8 (R8 - VAL-ROI-GEOM): Rechaza ROIs infinitesimales con área < 0.01."""
        # ancho = 0.05, alto = 0.05 -> area = 0.0025 < 0.01
        area_infinitesimal = AreaConfigDTO(
            id_area_vision=self.id_area_ent,
            id_camara=self.id_cam_ent,
            codigo="ROI-MINI",
            nombre="Área Infinitesimal",
            tipo_movimiento="ENTRADA",
            x_min=0.400, y_min=0.400, x_max=0.450, y_max=0.450,
            activa=True,
        )
        cams = [self.valid_cam_entrada, self.valid_cam_salida]
        areas = [area_infinitesimal, self.valid_area_salida]

        result = self.validator.validate(cameras=cams, areas=areas)

        self.assertFalse(result.is_valid)
        self.assertEqual(result.error_code, TopologyErrorCode.ERR_ROI_DEGENERADA)
        self.assertIn("degeneradas", result.error_detail)

    def test_third_camera_inactive_does_not_affect(self):
        """Una tercera cámara administrativa inactiva o sin áreas no afecta la topología nominal."""
        cam_aux = CameraConfigDTO(
            id_camara=uuid4(),
            codigo="CAM-MANTENIMIENTO",
            nombre="Cámara Auxiliar",
            uri_stream="rtsp://...",
            activa=False,  # Inactiva
        )
        cams = [self.valid_cam_entrada, self.valid_cam_salida, cam_aux]
        areas = [self.valid_area_entrada, self.valid_area_salida]

        result = self.validator.validate(cameras=cams, areas=areas)

        self.assertTrue(result.is_valid)

    # --------------------------------------------------------------------------
    # Repositorio inyectable y errores de conexión
    # --------------------------------------------------------------------------

    def test_database_connection_error_handling(self):
        """Rechaza con ERR_BD_CONEXION ante excepciones del repositorio."""
        mock_repo = MagicMock(spec=ITopologyConfigRepository)
        mock_repo.get_cameras.side_effect = ConnectionError("PostgreSQL connection timeout (port 5432 unreachable)")

        validator = TopologyValidator(repository=mock_repo)
        result = validator.validate()

        self.assertFalse(result.is_valid)
        self.assertEqual(result.error_code, TopologyErrorCode.ERR_BD_CONEXION)
        self.assertIn("PostgreSQL connection timeout", result.error_detail)

    # --------------------------------------------------------------------------
    # Integración con el inicio del motor propio (Bloqueo de captura e inferencia)
    # --------------------------------------------------------------------------

    def test_validation_failure_blocks_capture_and_inference(self):
        """Confirmación de que un fallo de topología impide abrir cámaras o ejecutar inferencia en VIGIA_Vision."""
        mock_cam = MagicMock(spec=IFrameCaptureSource)
        mock_detector = MagicMock(spec=IVehicleDetector)

        # Validador con error (falta CAM-SALIDA)
        mock_repo = MagicMock(spec=ITopologyConfigRepository)
        mock_repo.get_cameras.return_value = [self.valid_cam_entrada]
        mock_repo.get_areas.return_value = [self.valid_area_entrada]
        invalid_val = TopologyValidator(repository=mock_repo)

        coordinator = VisionEngineCoordinator(
            topology_validator=invalid_val,
            detector=mock_detector,
            source_factory=lambda _cam: mock_cam,
        )

        # Debe lanzar TopologyValidationError al inicializar y al intentar procesar
        with self.assertRaises(TopologyValidationError) as ctx:
            coordinator.initialize(open_sources=True)

        self.assertEqual(ctx.exception.error_code, TopologyErrorCode.ERR_CAM_SALIDA_FALTANTE)
        self.assertFalse(coordinator.is_initialized)

        with self.assertRaises(TopologyValidationError):
            coordinator.process_camera_step("CAM-ENTRADA")

        # Aserción crítica: NO se abrió ni leyó la cámara y NO se ejecutó inferencia
        mock_cam.open.assert_not_called()
        mock_cam.read_frame.assert_not_called()
        mock_detector.detect.assert_not_called()

    def test_initialize_vision_service_fail_fast(self):
        """VisionEngineCoordinator.initialize() con topología inválida aborta el inicio con TopologyValidationError."""
        mock_repo = MagicMock(spec=ITopologyConfigRepository)
        mock_repo.get_cameras.return_value = []
        mock_repo.get_areas.return_value = []
        invalid_val = TopologyValidator(repository=mock_repo)

        coordinator = VisionEngineCoordinator(topology_validator=invalid_val)
        with self.assertRaises(TopologyValidationError):
            coordinator.initialize(open_sources=True)
        self.assertFalse(coordinator.is_initialized)


if __name__ == "__main__":
    unittest.main()
