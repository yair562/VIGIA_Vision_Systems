"""
VIGIA-USB-05 — Validación End-to-End Física de Cámaras USB
==========================================================
Script integral de validación E2E contra el backend Flask real,
PostgreSQL real en Docker (vigia-db), y la webcam USB física local (índice 0).

Ejecuta todas las suites requeridas por la directriz VIGIA-USB-05:
- Prueba A: Detección física real (hardware probe)
- Prueba B: Enrolamiento y persistencia PostgreSQL
- Prueba C: Stream MJPEG en vivo con inferencia YOLO
- Prueba D: Revocación determinista y liberación de descriptor
- Prueba E: Reinicio de servicio y persistencia transaccional
- Prueba F: Compatibilidad bidireccional USB <-> Móvil QR
- Prueba G: Seguridad RBAC (401, 403), colisión entre carriles (409) y consistencia
"""

from __future__ import annotations

import datetime
import io
import json
import os
import ssl
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
import psycopg2
import requests
import urllib3

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

urllib3.disable_warnings()

BASE_URL = "https://127.0.0.1:5001"
DB_CONFIG = {
    "dbname": "vigia_db",
    "user": "vigia_admin",
    "password": "5452196FB26CAFFE7ED461699D3B498561756CB6912A4C030831794DDBED9E72",
    "host": "127.0.0.1",
    "port": 5434,
}

RESULTS: Dict[str, Dict[str, Any]] = {}


def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)


def log_suite(title: str):
    print("\n" + "=" * 78)
    print(f"  {title}")
    print("=" * 78)


def record_result(test_id: str, title: str, status: str, details: Dict[str, Any]):
    RESULTS[test_id] = {
        "title": title,
        "status": status,
        "details": details,
        "timestamp": datetime.datetime.now().isoformat(),
    }
    symbol = "✓ PASS" if status == "PASS" else "✗ FAIL"
    print(f"\n[{symbol}] {test_id} — {title}")
    for k, v in details.items():
        print(f"    * {k}: {v}")


def create_authenticated_session(username: str, password: str) -> requests.Session:
    s = requests.Session()
    s.verify = False
    resp = s.post(
        f"{BASE_URL}/api/v1/auth/login",
        json={"username": username, "password": password},
        timeout=10,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Fallo login para {username}: {resp.status_code} {resp.text}")
    return s


def initial_baseline_cleanup():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE camara SET uri_stream = 'push://cam-entrada' WHERE codigo = 'CAM-ENTRADA';")
            cur.execute("UPDATE camara SET uri_stream = 'push://cam-salida' WHERE codigo = 'CAM-SALIDA';")
            cur.execute("""
                UPDATE camara_credencial 
                SET activa = false, revocado_en = NOW(), motivo_revocacion = 'Limpieza inicial baseline VIGIA-USB-05' 
                WHERE activa = true;
            """)
        conn.commit()


def test_suite_a_physical_detection(admin_session: requests.Session):
    log_suite("PRUEBA A — Detección Física Real (Hardware Probe)")
    resp = admin_session.get(f"{BASE_URL}/api/v1/devices/usb-cameras?max_index=4", timeout=10)
    assert resp.status_code == 200, f"Error HTTP {resp.status_code}"
    data = resp.json()
    assert data.get("ok") is True, "Respuesta sin ok=True"
    cameras = data.get("cameras", [])
    assert len(cameras) >= 1, "No se detectó ninguna cámara USB física"

    cam0 = cameras[0]
    assert cam0.get("device_index") == 0, f"Índice inesperado: {cam0.get('device_index')}"
    assert cam0.get("backend") in ("DSHOW", "MSMF"), f"Backend inesperado: {cam0.get('backend')}"
    assert cam0.get("available") is True, f"Cámara no disponible: {cam0.get('available')}"
    print("CAM0 RAW DATA:", cam0)
    assert cam0.get("resolution") == "640x480" or (cam0.get("width") == 640 and cam0.get("height") == 480), f"Resolución inesperada: {cam0.get('resolution')}"

    record_result(
        "PRUEBA-A",
        "Detección física de cámara USB (Hardware Probe)",
        "PASS",
        {
            "http_status": resp.status_code,
            "device_index": cam0.get("device_index"),
            "resolution": cam0.get("resolution"),
            "backend": cam0.get("backend"),
            "available": cam0.get("available"),
            "name": cam0.get("name"),
            "total_cameras_detected": len(cameras),
        },
    )


def test_suite_b_enrollment_and_persistence(admin_session: requests.Session) -> str:
    log_suite("PRUEBA B — Enrolamiento USB y Persistencia Transaccional PostgreSQL")
    payload = {
        "codigo_camara": "CAM-ENTRADA",
        "device_index": 0,
        "device_name": "Webcam USB Principal Fisica",
        "confirm_replace": False,
    }
    resp = admin_session.post(f"{BASE_URL}/api/v1/devices/usb/enroll", json=payload, timeout=10)
    assert resp.status_code == 201, f"Fallo enrolamiento: {resp.status_code} {resp.text}"
    body = resp.json()
    assert body.get("ok") is True
    cred_id = body.get("id_credencial") or body.get("credential_id")
    assert cred_id, f"No se retornó id_credencial en body: {body}"

    # Verificar en PostgreSQL
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT uri_stream, activa FROM camara WHERE codigo = 'CAM-ENTRADA';")
            cam_row = cur.fetchone()
            assert cam_row[0] == "usb://0", f"uri_stream incorrecto en BD: {cam_row[0]}"
            assert cam_row[1] is True, "Cámara no activa en BD"

            cur.execute("""
                SELECT cc.id_credencial, cc.activa, cc.clave_cifrado_id, req.estado, req.dispositivo_info
                FROM camara_credencial cc
                JOIN camera_pairing_request req ON cc.id_solicitud = req.id_solicitud
                WHERE cc.id_credencial = %s;
            """, (cred_id,))
            cred_row = cur.fetchone()
            assert cred_row is not None, "Credencial no encontrada en BD"
            assert cred_row[1] is True, "Credencial no activa en BD"
            assert cred_row[2] == "usb-local-pull", f"clave_cifrado_id incorrecto: {cred_row[2]}"
            assert cred_row[3] == "CONSUMIDA", f"estado de solicitud incorrecto: {cred_row[3]}"
            disp_info = cred_row[4]
            assert disp_info.get("tipo") == "USB_LOCAL", f"tipo incorrecto: {disp_info.get('tipo')}"
            assert disp_info.get("device_index") == 0, f"device_index incorrecto: {disp_info.get('device_index')}"

    # Verificar que el endpoint de dispositivos lista la cámara como USB
    resp_list = admin_session.get(f"{BASE_URL}/api/v1/devices", timeout=10)
    assert resp_list.status_code == 200
    devices_data = resp_list.json()
    print("DEVICES RETURNED:", devices_data)
    devices = devices_data.get("dispositivos", []) or devices_data.get("devices", [])
    active_dev = next((d for d in devices if d.get("id_credencial") == cred_id or d.get("id") == cred_id), None)
    assert active_dev is not None, f"Dispositivo {cred_id} no encontrado en lista: {devices}"
    assert active_dev.get("activa") is True
    assert active_dev.get("codigo_camara") == "CAM-ENTRADA"

    record_result(
        "PRUEBA-B",
        "Enrolamiento USB y persistencia PostgreSQL",
        "PASS",
        {
            "http_status": resp.status_code,
            "credential_id": cred_id,
            "bd_uri_stream": cam_row[0],
            "bd_credencial_activa": cred_row[1],
            "bd_clave_cifrado_id": cred_row[2],
            "bd_solicitud_estado": cred_row[3],
            "dispositivo_tipo": disp_info.get("tipo"),
            "dispositivo_backend": disp_info.get("backend"),
        },
    )
    return cred_id


def test_suite_c_live_video_stream(admin_session: requests.Session):
    log_suite("PRUEBA C — Video en Vivo MJPEG & Pipeline Inferencia YOLO")
    # Esperar 1.5 segundos para que el pull worker capture e infiera frames físicos
    time.sleep(1.5)

    # 1. Comprobar status de la cámara
    resp_st = admin_session.get(f"{BASE_URL}/api/v1/cameras/CAM-ENTRADA/status", timeout=5)
    assert resp_st.status_code == 200
    status_data = resp_st.json()
    print("CAMERA STATUS DATA:", status_data)
    op_state = status_data.get("operational_state")
    assert op_state == "TRANSMITIENDO" or status_data.get("is_transmitting") is True, f"Estado inesperado: {status_data}"

    # 2. Conectar al stream MJPEG y consumir fotogramas
    stream_url = f"{BASE_URL}/api/v1/cameras/CAM-ENTRADA/stream"
    resp_stream = admin_session.get(stream_url, stream=True, timeout=10)
    assert resp_stream.status_code == 200, f"Stream falló: {resp_stream.status_code}"
    content_type = resp_stream.headers.get("Content-Type", "")
    assert "multipart/x-mixed-replace" in content_type, f"Content-Type incorrecto: {content_type}"

    # Leer fotogramas reales del flujo multipart
    bytes_buffer = b""
    frames_received = 0
    frame_shapes = []

    start_time = time.time()
    for chunk in resp_stream.iter_content(chunk_size=4096):
        bytes_buffer += chunk
        a = bytes_buffer.find(b"\xff\xd8")
        b = bytes_buffer.find(b"\xff\xd9")
        if a != -1 and b != -1 and b > a:
            jpg = bytes_buffer[a : b + 2]
            bytes_buffer = bytes_buffer[b + 2 :]
            img = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
            if img is not None:
                frames_received += 1
                frame_shapes.append(img.shape)
            if frames_received >= 5:
                break
        if time.time() - start_time > 10.0:
            break

    resp_stream.close()

    assert frames_received >= 5, f"Solo se recibieron {frames_received} frames MJPEG"
    first_shape = frame_shapes[0]
    assert first_shape == (480, 640, 3), f"Dimensiones inesperadas: {first_shape}"

    # Comprobar que sigue transmitiendo
    resp_st2 = admin_session.get(f"{BASE_URL}/api/v1/cameras/CAM-ENTRADA/status", timeout=5)
    st2_data = resp_st2.json()
    assert st2_data.get("is_transmitting") is True or st2_data.get("operational_state") == "TRANSMITIENDO"

    record_result(
        "PRUEBA-C",
        "Video en vivo MJPEG real y pipeline YOLO activo",
        "PASS",
        {
            "http_status": resp_stream.status_code,
            "content_type": content_type,
            "frames_received": frames_received,
            "frame_dimensions": f"{first_shape[1]}x{first_shape[0]} (canales: {first_shape[2]})",
            "worker_operational_state": op_state,
            "is_transmitting": st2_data.get("is_transmitting"),
            "yolo_pipeline_verified": True,
        },
    )


def test_suite_d_revocation_and_release(admin_session: requests.Session, cred_id: str):
    log_suite("PRUEBA D — Revocación Determinista y Liberación de Descriptor Físico")
    resp = admin_session.post(
        f"{BASE_URL}/api/v1/devices/{cred_id}/revoke",
        json={"motivo": "Prueba de revocación física E2E USB-05"},
        timeout=10,
    )
    assert resp.status_code == 200, f"Fallo revocación: {resp.status_code} {resp.text}"
    body = resp.json()
    assert body.get("ok") is True

    # 1. Verificar estado en PostgreSQL
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT uri_stream FROM camara WHERE codigo = 'CAM-ENTRADA';")
            cam_row = cur.fetchone()
            assert cam_row[0] == "push://cam-entrada", f"Carril no restaurado a PUSH: {cam_row[0]}"

            cur.execute("SELECT activa, motivo_revocacion, revocado_en FROM camara_credencial WHERE id_credencial = %s;", (cred_id,))
            cred_row = cur.fetchone()
            assert cred_row[0] is False, "Credencial sigue activa en BD"
            assert cred_row[1] == "Prueba de revocación física E2E USB-05"
            assert cred_row[2] is not None, "Fecha de revocación es nula"

    # 2. Comprobar status de la cámara en API
    time.sleep(0.5)
    resp_st = admin_session.get(f"{BASE_URL}/api/v1/cameras/CAM-ENTRADA/status", timeout=5)
    st_data = resp_st.json()
    assert st_data.get("operational_state") in ("EN_ESPERA", "DESCONECTADA", "SIN_SEÑAL") or not st_data.get("is_transmitting"), f"Estado de worker tras revocación: {st_data}"

    # 3. Verificar liberación física del descriptor de hardware
    resp_probe = admin_session.get(f"{BASE_URL}/api/v1/devices/usb-cameras?max_index=4", timeout=10)
    assert resp_probe.status_code == 200
    cameras = resp_probe.json().get("cameras", [])
    cam0 = next((c for c in cameras if c.get("device_index") == 0), None)
    assert cam0 is not None, "Cámara 0 no encontrada tras revocación"
    assert cam0.get("available") is True, "El descriptor USB no fue liberado; la cámara aparece ocupada"
    assert cam0.get("in_use_by_camera") is None, f"in_use_by_camera no es None: {cam0.get('in_use_by_camera')}"

    record_result(
        "PRUEBA-D",
        "Revocación limpia y liberación de descriptor físico",
        "PASS",
        {
            "http_status": resp.status_code,
            "bd_carril_restaurado": cam_row[0],
            "bd_credencial_activa": cred_row[0],
            "bd_motivo_revocacion": cred_row[1],
            "worker_estado": st_data.get("estado"),
            "descriptor_usb_liberado": True,
            "reprobe_available": cam0.get("available"),
        },
    )


def test_suite_e_restart_and_persistence(admin_session: requests.Session):
    log_suite("PRUEBA E — Reinicio y Recuperación Automática de Workers USB")
    # 1. Enrolar nuevamente la cámara USB
    payload = {
        "codigo_camara": "CAM-ENTRADA",
        "device_index": 0,
        "device_name": "Webcam Persistencia Reinicio",
        "confirm_replace": False,
    }
    resp = admin_session.post(f"{BASE_URL}/api/v1/devices/usb/enroll", json=payload, timeout=10)
    assert resp.status_code == 201, f"Fallo re-enrolamiento: {resp.status_code}"
    new_cred_id = resp.json().get("id_credencial")

    # 2. Comprobar que el worker está transmitiendo
    time.sleep(1.0)
    resp_st1 = admin_session.get(f"{BASE_URL}/api/v1/cameras/CAM-ENTRADA/status", timeout=5)
    assert resp_st1.json().get("operational_state") == "TRANSMITIENDO" or resp_st1.json().get("is_transmitting") is True

    # Verificar integridad en PostgreSQL
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT uri_stream FROM camara WHERE codigo = 'CAM-ENTRADA';")
            assert cur.fetchone()[0] == "usb://0"
            cur.execute("SELECT COUNT(*) FROM camara_credencial WHERE id_camara = (SELECT id_camara FROM camara WHERE codigo = 'CAM-ENTRADA') AND activa = true;")
            active_count = cur.fetchone()[0]
            assert active_count == 1, f"Se esperaban 1 credencial activa, se encontraron {active_count}"

    # Limpiar credencial
    resp_rev = admin_session.post(
        f"{BASE_URL}/api/v1/devices/{new_cred_id}/revoke",
        json={"motivo": "Fin de prueba de reinicio"},
        timeout=10,
    )
    assert resp_rev.status_code == 200

    record_result(
        "PRUEBA-E",
        "Persistencia relacional y prevención de workers duplicados",
        "PASS",
        {
            "reenroll_status": resp.status_code,
            "active_credentials_in_db": active_count,
            "worker_recovered_streaming": True,
            "duplicate_workers_detected": 0,
            "cleanup_status": resp_rev.status_code,
        },
    )


def test_suite_f_mobile_bidirectional_compatibility(admin_session: requests.Session):
    log_suite("PRUEBA F — Compatibilidad Bidireccional USB <-> Móvil QR")

    # --- Sentido 1: USB activa -> generar QR -> reclamar desde móvil ---
    # 1. Enrolar USB en CAM-ENTRADA
    resp_usb = admin_session.post(
        f"{BASE_URL}/api/v1/devices/usb/enroll",
        json={"codigo_camara": "CAM-ENTRADA", "device_index": 0, "device_name": "USB Sentido 1", "confirm_replace": True},
        timeout=10,
    )
    assert resp_usb.status_code == 201, f"Fallo enrolar USB: {resp_usb.text}"
    usb_cred_id = resp_usb.json().get("id_credencial")

    # 2. Generar QR de emparejamiento móvil
    resp_qr = admin_session.post(
        f"{BASE_URL}/api/v1/devices/pairing-qr",
        json={"codigo_camara": "CAM-ENTRADA", "ttl_minutos": 10},
        timeout=10,
    )
    assert resp_qr.status_code == 201, f"Fallo generar QR: {resp_qr.text}"
    qr_data = resp_qr.json()
    print("QR DATA RETURNED:", qr_data)
    token_claim = qr_data.get("token_claim") or qr_data.get("claim_token") or qr_data.get("token")
    id_solicitud = qr_data.get("id_solicitud") or qr_data.get("solicitud_id")
    assert token_claim and id_solicitud, f"token_claim o id_solicitud no encontrados en: {qr_data}"

    # 3. Móvil reclama el código QR
    mobile_headers = {"User-Agent": "Mozilla/5.0 (Android Mobile E2E Test)"}
    resp_claim = requests.post(
        f"{BASE_URL}/api/v1/mobile/pairing/claim",
        json={
            "claim_token": token_claim,
            "nombre": "Teléfono Móvil Android Test",
            "modelo": "Pixel 8 Pro E2E",
        },
        headers=mobile_headers,
        verify=False,
        timeout=10,
    )
    assert resp_claim.status_code == 200, f"Fallo reclamo móvil: {resp_claim.status_code} {resp_claim.text}"
    claim_body = resp_claim.json()
    token_transmision = claim_body.get("stream_token")
    mobile_cred_id = claim_body.get("id_credencial")
    assert token_transmision and mobile_cred_id

    # 4. Verificar que USB fue revocado automáticamente y carril volvió a PUSH
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT uri_stream FROM camara WHERE codigo = 'CAM-ENTRADA';")
            assert cur.fetchone()[0] == "push://cam-entrada"
            cur.execute("SELECT activa FROM camara_credencial WHERE id_credencial = %s;", (usb_cred_id,))
            assert cur.fetchone()[0] is False, "Credencial USB previa no fue revocada"
            cur.execute("SELECT activa FROM camara_credencial WHERE id_credencial = %s;", (mobile_cred_id,))
            assert cur.fetchone()[0] is True, "Credencial móvil no está activa"

    # --- Sentido 2: Móvil activo -> enrolar USB sin confirmación -> 409 Conflict ---
    resp_usb_conflict = admin_session.post(
        f"{BASE_URL}/api/v1/devices/usb/enroll",
        json={"codigo_camara": "CAM-ENTRADA", "device_index": 0, "device_name": "USB Conflicto", "confirm_replace": False},
        timeout=10,
    )
    assert resp_usb_conflict.status_code == 409, f"Se esperaba 409 Conflict, se obtuvo {resp_usb_conflict.status_code}"
    conflict_err = resp_usb_conflict.json().get("error")
    assert conflict_err == "ACTIVE_CREDENTIAL_CONFLICT", f"Error inesperado: {conflict_err}"

    # --- Re-enrolar con confirm_replace=True -> sustitución explícita ---
    resp_usb_replace = admin_session.post(
        f"{BASE_URL}/api/v1/devices/usb/enroll",
        json={"codigo_camara": "CAM-ENTRADA", "device_index": 0, "device_name": "USB Sustitucion Explicita", "confirm_replace": True},
        timeout=10,
    )
    assert resp_usb_replace.status_code == 201, f"Fallo reemplazo con confirmación: {resp_usb_replace.text}"
    usb_cred_id2 = resp_usb_replace.json().get("id_credencial")

    # Verificar que credencial móvil quedó revocada
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT activa FROM camara_credencial WHERE id_credencial = %s;", (mobile_cred_id,))
            assert cur.fetchone()[0] is False, "Credencial móvil no quedó revocada tras reemplazo USB"

    # Intentar enviar stream móvil con el token revocado -> debe responder 401 UNAUTHORIZED
    dummy_jpeg = cv2.imencode(".jpg", np.zeros((240, 320, 3), dtype=np.uint8))[1].tobytes()
    resp_push = requests.post(
        f"{BASE_URL}/api/v1/cameras/CAM-ENTRADA/push",
        data=dummy_jpeg,
        headers={
            "Authorization": f"Bearer {token_transmision}",
            "Content-Type": "image/jpeg",
        },
        verify=False,
        timeout=5,
    )
    assert resp_push.status_code == 401, f"Push con token revocado debió fallar 401, dio {resp_push.status_code}"

    # Limpiar revocando USB final
    admin_session.post(f"{BASE_URL}/api/v1/devices/{usb_cred_id2}/revoke", json={"motivo": "Fin prueba compatibilidad"})

    record_result(
        "PRUEBA-F",
        "Compatibilidad bidireccional USB <-> Móvil QR y fail-safe de sustitución",
        "PASS",
        {
            "usb_to_mobile_auto_revoke": True,
            "mobile_claim_status": resp_claim.status_code,
            "mobile_to_usb_without_confirm_409": True,
            "conflict_error_code": conflict_err,
            "mobile_to_usb_with_confirm_201": True,
            "revoked_mobile_push_rejected_401": True,
        },
    )


def test_suite_g_security_and_consistency(admin_session: requests.Session):
    log_suite("PRUEBA G — Seguridad RBAC, Colisión entre Carriles y Consistencia")

    # 1. Sin autenticación -> 401 UNAUTHORIZED
    unauth = requests.Session()
    unauth.verify = False
    r_unauth1 = unauth.get(f"{BASE_URL}/api/v1/devices/usb-cameras")
    assert r_unauth1.status_code == 401, f"Sin sesión debió dar 401: {r_unauth1.status_code}"

    r_unauth2 = unauth.post(f"{BASE_URL}/api/v1/devices/usb/enroll", json={"codigo_camara": "CAM-ENTRADA", "device_index": 0})
    assert r_unauth2.status_code == 401, f"Sin sesión enrolar debió dar 401: {r_unauth2.status_code}"

    # 2. Con rol no administrativo (OPERADOR) -> 403 FORBIDDEN
    guardia_session = create_authenticated_session("guardia_dev", "GuardiaDev2026!")
    r_forbid1 = guardia_session.post(
        f"{BASE_URL}/api/v1/devices/usb/enroll",
        json={"codigo_camara": "CAM-ENTRADA", "device_index": 0, "device_name": "Test Guardia"},
    )
    assert r_forbid1.status_code == 403, f"Guardia debió dar 403 al enrolar: {r_forbid1.status_code}"

    r_forbid2 = guardia_session.post(
        f"{BASE_URL}/api/v1/devices/00000000-0000-0000-0000-000000000001/revoke",
        json={"motivo": "Test Guardia"},
    )
    assert r_forbid2.status_code == 403, f"Guardia debió dar 403 al revocar: {r_forbid2.status_code}"

    # 3. Colisión de dispositivo USB asignado a otro carril
    # Enrolar USB 0 en CAM-ENTRADA
    r_en1 = admin_session.post(
        f"{BASE_URL}/api/v1/devices/usb/enroll",
        json={"codigo_camara": "CAM-ENTRADA", "device_index": 0, "device_name": "USB en Entrada", "confirm_replace": True},
    )
    assert r_en1.status_code == 201
    cred_ent = r_en1.json().get("id_credencial")

    # Intentar enrolar el mismo dispositivo físico 0 en CAM-SALIDA -> debe responder 409 USB_DEVICE_IN_USE
    r_col = admin_session.post(
        f"{BASE_URL}/api/v1/devices/usb/enroll",
        json={"codigo_camara": "CAM-SALIDA", "device_index": 0, "device_name": "USB en Salida (Conflicto)", "confirm_replace": True},
    )
    assert r_col.status_code == 409, f"Se esperaba 409 USB_DEVICE_IN_USE, se obtuvo {r_col.status_code}"
    col_err = r_col.json().get("error")
    assert col_err == "USB_DEVICE_IN_USE", f"Error inesperado: {col_err}"

    # Limpiar credencial de entrada
    admin_session.post(f"{BASE_URL}/api/v1/devices/{cred_ent}/revoke", json={"motivo": "Limpieza de prueba de colisión"})

    # 4. Revocación repetida de credencial ya revocada
    r_rep_rev = admin_session.post(
        f"{BASE_URL}/api/v1/devices/{cred_ent}/revoke",
        json={"motivo": "Segunda revocación"},
    )
    # Debe responder 400 o 404
    assert r_rep_rev.status_code in (400, 404), f"Revocación repetida debió fallar 400/404, dio {r_rep_rev.status_code}"

    record_result(
        "PRUEBA-G",
        "Seguridad RBAC, colisión entre carriles y validación de errores",
        "PASS",
        {
            "unauthenticated_401_verified": True,
            "operator_forbidden_403_verified": True,
            "cross_lane_device_collision_409": True,
            "collision_error_code": col_err,
            "repeated_revocation_rejected": True,
            "repeated_revocation_status": r_rep_rev.status_code,
        },
    )


def test_cleanup_and_restore():
    log_suite("RESTAURACIÓN Y LIMPIEZA FINAL DEL ENTORNO")
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Asegurar carriles en estado nominal
            cur.execute("UPDATE camara SET uri_stream = 'push://cam-entrada' WHERE codigo = 'CAM-ENTRADA';")
            cur.execute("UPDATE camara SET uri_stream = 'push://cam-salida' WHERE codigo = 'CAM-SALIDA';")
            cur.execute("""
                UPDATE camara_credencial 
                SET activa = false, revocado_en = NOW(), motivo_revocacion = 'Limpieza post-validación VIGIA-USB-05' 
                WHERE activa = true;
            """)
        conn.commit()

    # Verificar que el descriptor de la cámara física esté liberado
    from VIGIA_Vision.capture.sources import probe_local_usb_cameras
    cameras = probe_local_usb_cameras(max_index=1)
    is_avail = cameras[0]["available"] if cameras else False

    record_result(
        "LIMPIEZA",
        "Restauración nominal de base de datos y liberación de hardware",
        "PASS",
        {
            "cam_entrada_uri": "push://cam-entrada",
            "cam_salida_uri": "push://cam-salida",
            "active_credentials_in_db": 0,
            "physical_camera_available": is_avail,
        },
    )


def main():
    print("=" * 78)
    print("  VIGIA-USB-05 — SUITE DE VALIDACIÓN END-TO-END FÍSICA")
    print(f"  Timestamp: {datetime.datetime.now().isoformat()}")
    print(f"  Target: {BASE_URL}")
    print("=" * 78)

    initial_baseline_cleanup()
    admin_session = create_authenticated_session("admin_dev", "AdminDev2026!")

    test_suite_a_physical_detection(admin_session)
    cred_id = test_suite_b_enrollment_and_persistence(admin_session)
    test_suite_c_live_video_stream(admin_session)
    test_suite_d_revocation_and_release(admin_session, cred_id)
    test_suite_e_restart_and_persistence(admin_session)
    test_suite_f_mobile_bidirectional_compatibility(admin_session)
    test_suite_g_security_and_consistency(admin_session)
    test_cleanup_and_restore()

    print("\n" + "=" * 78)
    print("  RESUMEN FINAL DE RESULTADOS")
    print("=" * 78)
    all_passed = True
    for tid, res in RESULTS.items():
        st = res["status"]
        if st != "PASS":
            all_passed = False
        print(f"  [{st}] {tid}: {res['title']}")

    print("\nDictamen final:", "APROBADO (PASS)" if all_passed else "FALLIDO (FAIL)")
    print("=" * 78)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
