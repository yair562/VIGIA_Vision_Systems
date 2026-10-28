"""
tests.unit.test_domain_models
=============================
Pruebas unitarias para los modelos canónicos inmutables de VIGIA_Core.
Verifica las invariantes de VisionResult y AccessDecision.
"""

import sys
import unittest
from datetime import datetime, timezone
from dataclasses import FrozenInstanceError
from pathlib import Path
from uuid import uuid4

# Asegurar rutas en sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from VIGIA_Core.domain.vision_result import VisionResult, VisionStatus
from VIGIA_Core.domain.access_decision import (
    AccessDecision,
    AccessResult,
    TipoMovimiento,
    TipoAcceso,
    MotivoDecision,
    AccessState,
)


class TestVisionResult(unittest.TestCase):
    def test_valid_confidence_and_nominal_creation(self):
        """PU-VR-01: Instanciación válida nominal con valores de confianza en rango [0.0, 1.0]."""
        res = VisionResult(
            status=VisionStatus.VEHICLE_DETECTED_PLATE_READ,
            vehicle_detected=True,
            vehicle_confidence=0.95,
            vehicle_type_pred="AUTOMOVIL",
            plate_located=True,
            plate_text="ABC1234",
            plate_confidence=0.88,
            evidence_path="evidencias/test.jpg",
        )
        self.assertEqual(res.status, VisionStatus.VEHICLE_DETECTED_PLATE_READ)
        self.assertTrue(res.vehicle_detected)
        self.assertEqual(res.vehicle_confidence, 0.95)
        self.assertEqual(res.plate_text, "ABC1234")
        self.assertEqual(res.plate_confidence, 0.88)
        self.assertFalse(res.is_technical_error)
        self.assertTrue(res.has_readable_plate)
        self.assertFalse(res.requires_guard_review)

    def test_boundary_confidence_values(self):
        """Valores límite exactos 0.0 y 1.0 son permitidos."""
        res_zero = VisionResult(
            status=VisionStatus.VEHICLE_DETECTED_NO_PLATE,
            vehicle_detected=True,
            vehicle_confidence=0.0,
        )
        self.assertEqual(res_zero.vehicle_confidence, 0.0)

        res_one = VisionResult(
            status=VisionStatus.VEHICLE_DETECTED_PLATE_READ,
            vehicle_detected=True,
            vehicle_confidence=1.0,
            plate_located=True,
            plate_text="XYZ999",
            plate_confidence=1.0,
        )
        self.assertEqual(res_one.vehicle_confidence, 1.0)
        self.assertEqual(res_one.plate_confidence, 1.0)

    def test_invalid_vehicle_confidence_negative(self):
        """PU-VR-05: Rechazo de confianza vehicular menor a 0.0."""
        with self.assertRaises(ValueError) as ctx:
            VisionResult(
                status=VisionStatus.VEHICLE_DETECTED_NO_PLATE,
                vehicle_detected=True,
                vehicle_confidence=-0.01,
            )
        self.assertIn("vehicle_confidence=-0.01 fuera del rango [0.0, 1.0]", str(ctx.exception))

    def test_invalid_vehicle_confidence_greater_than_one(self):
        """PU-VR-06: Rechazo de confianza vehicular mayor a 1.0."""
        with self.assertRaises(ValueError) as ctx:
            VisionResult(
                status=VisionStatus.VEHICLE_DETECTED_NO_PLATE,
                vehicle_detected=True,
                vehicle_confidence=1.001,
            )
        self.assertIn("vehicle_confidence=1.001 fuera del rango [0.0, 1.0]", str(ctx.exception))

    def test_invalid_plate_confidence_negative(self):
        """PU-VR-07: Rechazo de confianza de placa menor a 0.0."""
        with self.assertRaises(ValueError) as ctx:
            VisionResult(
                status=VisionStatus.VEHICLE_DETECTED_PLATE_READ,
                plate_text="ABC1234",
                plate_confidence=-0.05,
            )
        self.assertIn("plate_confidence=-0.05 fuera del rango [0.0, 1.0]", str(ctx.exception))

    def test_invalid_plate_confidence_greater_than_one(self):
        """PU-VR-08: Rechazo de confianza de placa mayor a 1.0."""
        with self.assertRaises(ValueError) as ctx:
            VisionResult(
                status=VisionStatus.VEHICLE_DETECTED_PLATE_READ,
                plate_text="ABC1234",
                plate_confidence=1.05,
            )
        self.assertIn("plate_confidence=1.05 fuera del rango [0.0, 1.0]", str(ctx.exception))

    def test_plate_text_present_without_confidence(self):
        """PU-VR-10: Rechazo de plate_text presente cuando plate_confidence es None."""
        with self.assertRaises(ValueError) as ctx:
            VisionResult(
                status=VisionStatus.VEHICLE_DETECTED_PLATE_READ,
                plate_text="ABC1234",
                plate_confidence=None,
            )
        self.assertIn("plate_text presente pero plate_confidence es None", str(ctx.exception))

    def test_camera_error_with_vehicle_detected_inconsistency(self):
        """PU-VR-11: Inconsistencia: CAMERA_ERROR no puede tener vehicle_detected=True."""
        with self.assertRaises(ValueError) as ctx:
            VisionResult(
                status=VisionStatus.CAMERA_ERROR,
                vehicle_detected=True,
            )
        self.assertIn("status=VisionStatus.CAMERA_ERROR no puede tener vehicle_detected=True", str(ctx.exception))

    def test_vision_error_with_vehicle_detected_inconsistency(self):
        """PU-VR-12: Inconsistencia: VISION_ERROR no puede tener vehicle_detected=True."""
        with self.assertRaises(ValueError) as ctx:
            VisionResult(
                status=VisionStatus.VISION_ERROR,
                vehicle_detected=True,
            )
        self.assertIn("status=VisionStatus.VISION_ERROR no puede tener vehicle_detected=True", str(ctx.exception))

    def test_immutability(self):
        """PU-VR-13: Inmutabilidad de VisionResult (frozen dataclass)."""
        res = VisionResult(status=VisionStatus.NO_VEHICLE_DETECTED)
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            res.status = VisionStatus.CAMERA_ERROR
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            res.vehicle_detected = True

    def test_inspector_properties(self):
        """PU-VR-14 a 16: Comportamiento de las propiedades inspectoras."""
        cam_err = VisionResult(status=VisionStatus.CAMERA_ERROR, vehicle_detected=False)
        self.assertTrue(cam_err.is_technical_error)
        self.assertFalse(cam_err.has_readable_plate)
        self.assertFalse(cam_err.requires_guard_review)

        unreadable = VisionResult(
            status=VisionStatus.VEHICLE_DETECTED_PLATE_UNREADABLE,
            vehicle_detected=True,
            vehicle_confidence=0.8,
        )
        self.assertFalse(unreadable.is_technical_error)
        self.assertFalse(unreadable.has_readable_plate)
        self.assertTrue(unreadable.requires_guard_review)

        no_plate = VisionResult(
            status=VisionStatus.VEHICLE_DETECTED_NO_PLATE,
            vehicle_detected=True,
            vehicle_confidence=0.8,
        )
        self.assertTrue(no_plate.requires_guard_review)


class TestAccessDecision(unittest.TestCase):
    def test_valid_automatic_access(self):
        """PU-AD-01: Instanciación válida de decisión automática."""
        dec = AccessDecision(
            result=AccessResult.PERMITIDO,
            motivo=MotivoDecision.VEHICULO_AUTORIZADO,
            tipo_movimiento=TipoMovimiento.ENTRADA,
            tipo_acceso=TipoAcceso.AUTOMATICO,
            ui_state=AccessState.ACCESO_PERMITIDO,
            hardware_command="ABRE",
        )
        self.assertEqual(dec.result, AccessResult.PERMITIDO)
        self.assertEqual(dec.motivo_ddl_v1, "VEHICULO_AUTORIZADO")

    def test_manual_supervisado_without_operator_raises(self):
        """PU-AD-02: MANUAL_SUPERVISADO con PERMITIDO requiere id_usuario_operador."""
        with self.assertRaises(ValueError) as ctx:
            AccessDecision(
                result=AccessResult.PERMITIDO,
                motivo=MotivoDecision.VISITA_JUSTIFICADA,
                tipo_movimiento=TipoMovimiento.ENTRADA,
                tipo_acceso=TipoAcceso.MANUAL_SUPERVISADO,
                ui_state=AccessState.ACCESO_PERMITIDO,
                id_usuario_operador=None,
            )
        self.assertIn("MANUAL_SUPERVISADO con PERMITIDO requiere id_usuario_operador", str(ctx.exception))

    def test_manual_supervisado_with_operator_succeeds(self):
        """PU-AD-03: MANUAL_SUPERVISADO con PERMITIDO con id_usuario_operador tiene éxito."""
        op_id = uuid4()
        dec = AccessDecision(
            result=AccessResult.PERMITIDO,
            motivo=MotivoDecision.VISITA_JUSTIFICADA,
            tipo_movimiento=TipoMovimiento.ENTRADA,
            tipo_acceso=TipoAcceso.MANUAL_SUPERVISADO,
            ui_state=AccessState.ACCESO_PERMITIDO,
            id_usuario_operador=op_id,
            hardware_command="ABRE",
        )
        self.assertEqual(dec.id_usuario_operador, op_id)

    def test_ddl_v1_safe_mapping(self):
        """PU-AD-04 y 05: Mapeo seguro para motivos transitorios no soportados por el DDL V1."""
        dec_sin_asoc = AccessDecision(
            result=AccessResult.DENEGADO,
            motivo=MotivoDecision.SIN_ASOCIACION_AUTORIZADA,
            tipo_movimiento=TipoMovimiento.ENTRADA,
            tipo_acceso=TipoAcceso.AUTOMATICO,
            ui_state=AccessState.SIN_AUTORIZACION,
        )
        self.assertEqual(dec_sin_asoc.motivo_ddl_v1, "VEHICULO_INACTIVO")

    def test_access_decision_immutability(self):
        """PU-AD-08: Inmutabilidad de AccessDecision."""
        dec = AccessDecision(
            result=AccessResult.DENEGADO,
            motivo=MotivoDecision.PLACA_NO_REGISTRADA,
            tipo_movimiento=TipoMovimiento.ENTRADA,
            tipo_acceso=TipoAcceso.AUTOMATICO,
            ui_state=AccessState.PLACA_NO_REGISTRADA,
        )
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            dec.result = AccessResult.PERMITIDO


if __name__ == "__main__":
    unittest.main()
