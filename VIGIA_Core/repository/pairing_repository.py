"""
VIGIA_Core.repository.pairing_repository
========================================
Repositorio PostgreSQL para solicitudes de enrolamiento QR (camera_pairing_request)
y credenciales individuales de transmisión (camara_credencial).
Implementa garantías ACID, expiración perezosa atómica y unicidad por cámara.
""" 

from __future__ import annotations

import hashlib
import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import psycopg2
from psycopg2.extras import RealDictCursor

from VIGIA_Core.domain.pairing import (
    ActiveDeviceDTO,
    CameraCredentialDTO,
    PairingRequestDTO,
    PairingRequestState,
)
from VIGIA_Core.repository.detection_repository import (
    DatabaseConnectionError,
    DatabasePersistenceError,
)

logger = logging.getLogger(__name__)


class ActiveCredentialConflictError(ValueError):
    """Se intentó activar una nueva fuente USB cuando existe una credencial activa sin confirmación."""

    def __init__(self, message: str, existing_info: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.existing_info = existing_info or {}


def hash_token_sha256(raw_token: str) -> str:
    """Calcula el digest hexadecimal SHA-256 de un token secreto."""
    if not raw_token or not isinstance(raw_token, str):
        raise ValueError("El token debe ser una cadena no vacía.")
    return hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()


class PsycopgPairingRepository:
    """Implementación de persistencia para el flujo de enrolamiento QR en PostgreSQL."""

    def __init__(self, dsn: str, connect_timeout: int = 5) -> None:
        self._dsn = dsn
        self._connect_timeout = connect_timeout

    def _get_connection(self):
        try:
            return psycopg2.connect(self._dsn, connect_timeout=self._connect_timeout)
        except Exception as exc:
            raise DatabaseConnectionError(
                f"Fallo al conectar con PostgreSQL para pairing_repository: {exc}"
            ) from exc

    def create_pairing_request(
        self,
        *,
        id_camara: UUID,
        token_claim_hash: str,
        creado_por: UUID,
        ttl_minutes: int = 10,
    ) -> PairingRequestDTO:
        """
        Crea una nueva solicitud de enrolamiento QR garantizando unicidad activa:
        1. Limpia atómicamente solicitudes CREADA/PENDIENTE expiradas para esa cámara.
        2. Si aún existe una solicitud CREADA o PENDIENTE vigente, cancela la previa para permitir el nuevo QR.
        3. Inserta la nueva solicitud en estado CREADA.
        """
        conn = self._get_connection()
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # 1. Limpiar solicitudes expiradas para liberar el índice parcial
                    cur.execute(
                        """
                        UPDATE camera_pairing_request
                        SET estado = 'EXPIRADA'
                        WHERE id_camara = %s
                          AND estado IN ('CREADA', 'PENDIENTE')
                          AND expira_en <= CURRENT_TIMESTAMP;
                        """,
                        (str(id_camara),),
                    )

                    # 2. Cancelar solicitudes vivas previas no expiradas de esa cámara
                    cur.execute(
                        """
                        UPDATE camera_pairing_request
                        SET estado = 'CANCELADA',
                            cancelado_en = CURRENT_TIMESTAMP,
                            resuelto_por = %s,
                            motivo_rechazo = 'Sustituida por nueva generación de QR'
                        WHERE id_camara = %s
                          AND estado IN ('CREADA', 'PENDIENTE');
                        """,
                        (str(creado_por), str(id_camara)),
                    )

                    # 3. Insertar la nueva solicitud
                    cur.execute(
                        """
                        INSERT INTO camera_pairing_request (
                            id_camara,
                            token_claim_hash,
                            estado,
                            creado_por,
                            expira_en
                        ) VALUES (
                            %s,
                            %s,
                            'CREADA',
                            %s,
                            CURRENT_TIMESTAMP + (%s || ' minutes')::interval
                        )
                        RETURNING *;
                        """,
                        (str(id_camara), token_claim_hash, str(creado_por), str(ttl_minutes)),
                    )
                    row = cur.fetchone()
                    return self._row_to_request_dto(row)
        except Exception as exc:
            raise DatabasePersistenceError(
                f"Error al crear solicitud de enrolamiento QR: {exc}"
            ) from exc
        finally:
            conn.close()

    def claim_pairing_request(
        self,
        *,
        token_claim_hash: str,
        token_poll_hash: str,
        dispositivo_info: Dict[str, Any],
    ) -> PairingRequestDTO:
        """
        El teléfono móvil presenta T_claim. Si la solicitud está CREADA y no ha expirado,
        se asocia el dispositivo y pasa a estado PENDIENTE.
        """
        conn = self._get_connection()
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        UPDATE camera_pairing_request
                        SET estado = 'PENDIENTE',
                            token_poll_hash = %s,
                            dispositivo_info = %s::jsonb,
                            reclamado_en = CURRENT_TIMESTAMP
                        WHERE token_claim_hash = %s
                          AND estado = 'CREADA'
                          AND expira_en > CURRENT_TIMESTAMP
                        RETURNING *;
                        """,
                        (token_poll_hash, json.dumps(dispositivo_info), token_claim_hash),
                    )
                    row = cur.fetchone()
                    if not row:
                        # Verificar si existe pero expiró
                        cur.execute(
                            """
                            SELECT estado, expira_en <= CURRENT_TIMESTAMP AS expirado
                            FROM camera_pairing_request
                            WHERE token_claim_hash = %s;
                            """,
                            (token_claim_hash,),
                        )
                        check = cur.fetchone()
                        if not check:
                            raise ValueError("TOKEN_NOT_FOUND")
                        if check["expirado"] or check["estado"] == "EXPIRADA":
                            raise ValueError("TOKEN_EXPIRED")
                        raise ValueError(f"INVALID_STATE_{check['estado']}")

                    return self._row_to_request_dto(row)
        except ValueError:
            raise
        except Exception as exc:
            raise DatabasePersistenceError(
                f"Error al reclamar solicitud de enrolamiento: {exc}"
            ) from exc
        finally:
            conn.close()

    def approve_and_issue_credential(
        self,
        *,
        id_solicitud: UUID,
        aprobado_por: UUID,
        token_transmision_hash: str,
        credencial_cifrada: str,
        clave_cifrado_id: str = "v1-plain-token",
    ) -> Tuple[PairingRequestDTO, CameraCredentialDTO]:
        """
        Aprobación administrativa de la solicitud:
        1. Transición de la solicitud a APROBADA.
        2. Revocación de cualquier credencial previa activa para esa misma cámara (invariante 1 activa).
        3. Emisión de la nueva credencial con el sobre cifrado temporal para entrega al móvil.
        """
        conn = self._get_connection()
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # 1. Actualizar solicitud
                    cur.execute(
                        """
                        UPDATE camera_pairing_request
                        SET estado = 'APROBADA',
                            resuelto_por = %s,
                            resuelto_en = CURRENT_TIMESTAMP
                        WHERE id_solicitud = %s
                          AND estado IN ('PENDIENTE', 'CREADA')
                          AND expira_en > CURRENT_TIMESTAMP
                        RETURNING *;
                        """,
                        (str(aprobado_por), str(id_solicitud)),
                    )
                    req_row = cur.fetchone()
                    if not req_row:
                        raise ValueError("SOLICITUD_NO_ELEGIBLE_PARA_APROBACION")

                    id_camara = req_row["id_camara"]

                    # 2. Revocar credencial previa activa si existiera
                    cur.execute(
                        """
                        UPDATE camara_credencial
                        SET activa = FALSE,
                            revocado_por = %s,
                            revocado_en = CURRENT_TIMESTAMP,
                            motivo_revocacion = 'Sustituida por nueva aprobacion de enrolamiento'
                        WHERE id_camara = %s
                          AND activa = TRUE;
                        """,
                        (str(aprobado_por), str(id_camara)),
                    )

                    # 3. Crear credencial nueva
                    cur.execute(
                        """
                        INSERT INTO camara_credencial (
                            id_camara,
                            id_solicitud,
                            token_transmision_hash,
                            clave_cifrado_id,
                            credencial_cifrada,
                            activa
                        ) VALUES (
                            %s, %s, %s, %s, %s, TRUE
                        )
                        RETURNING *;
                        """,
                        (
                            str(id_camara),
                            str(id_solicitud),
                            token_transmision_hash,
                            clave_cifrado_id,
                            credencial_cifrada,
                        ),
                    )
                    cred_row = cur.fetchone()

                    req_dto = self._row_to_request_dto(req_row)
                    cred_dto = self._row_to_cred_dto(cred_row)
                    return req_dto, cred_dto
        except ValueError:
            raise
        except Exception as exc:
            raise DatabasePersistenceError(
                f"Error al aprobar solicitud y emitir credencial: {exc}"
            ) from exc
        finally:
            conn.close()

    def get_poll_status_and_credential(
        self,
        *,
        token_poll_hash: str,
    ) -> Tuple[PairingRequestDTO, Optional[str]]:
        """
        El móvil sondea el estado de su solicitud usando su token_poll.
        Si fue APROBADA, incrementa el contador de entregas y entrega credencial_cifrada.
        """
        conn = self._get_connection()
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT * FROM camera_pairing_request
                        WHERE token_poll_hash = %s;
                        """,
                        (token_poll_hash,),
                    )
                    req_row = cur.fetchone()
                    if not req_row:
                        raise ValueError("POLL_TOKEN_NOT_FOUND")

                    req_dto = self._row_to_request_dto(req_row)
                    if req_dto.estado != PairingRequestState.APROBADA:
                        return req_dto, None

                    # Buscar credencial asociada
                    cur.execute(
                        """
                        UPDATE camara_credencial
                        SET intentos_entrega = LEAST(intentos_entrega + 1, 5)
                        WHERE id_solicitud = %s
                        RETURNING credencial_cifrada, intentos_entrega;
                        """,
                        (str(req_dto.id_solicitud),),
                    )
                    cred_row = cur.fetchone()
                    encrypted_payload = cred_row["credencial_cifrada"] if cred_row else None
                    return req_dto, encrypted_payload
        except ValueError:
            raise
        except Exception as exc:
            raise DatabasePersistenceError(
                f"Error en sondeo de estado de solicitud: {exc}"
            ) from exc
        finally:
            conn.close()

    def confirm_credential_receipt(
        self,
        *,
        token_poll_hash: str,
    ) -> bool:
        """
        El móvil confirma que recibió y guardó la credencial.
        Transiciona la solicitud a CONSUMIDA y purga credencial_cifrada a NULL.
        """
        conn = self._get_connection()
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        UPDATE camera_pairing_request
                        SET estado = 'CONSUMIDA',
                            consumido_en = CURRENT_TIMESTAMP
                        WHERE token_poll_hash = %s
                          AND estado = 'APROBADA'
                        RETURNING id_solicitud;
                        """,
                        (token_poll_hash,),
                    )
                    row = cur.fetchone()
                    if not row:
                        return False

                    id_solicitud = row["id_solicitud"]
                    cur.execute(
                        """
                        UPDATE camara_credencial
                        SET credencial_cifrada = NULL,
                            entregado_en = CURRENT_TIMESTAMP
                        WHERE id_solicitud = %s;
                        """,
                        (str(id_solicitud),),
                    )
                    return True
        except Exception as exc:
            raise DatabasePersistenceError(
                f"Error al confirmar recepción de credencial: {exc}"
            ) from exc
        finally:
            conn.close()

    def enroll_usb_device(
        self,
        *,
        id_camara: UUID,
        codigo_camara: str,
        device_index: int,
        device_name: str,
        creado_por: UUID,
        dispositivo_info: Dict[str, Any],
        replace_active: bool = False,
    ) -> Tuple[PairingRequestDTO, CameraCredentialDTO]:
        """
        Registra y activa transaccionalmente una cámara local USB sobre una cámara lógica.

        Cumple íntegramente el DDL V004 sin migraciones adicionales:
        1. Bloquea la cámara lógica en `camara` y comprueba si existe credencial activa.
        2. Si existe credencial activa y `replace_active` es False, aborta con
           `ActiveCredentialConflictError` sin revocar automáticamente dispositivos previos.
        3. Si `replace_active` es True, revoca explícitamente la credencial anterior y
           cancela solicitudes QR vivas para liberar los índices parciales de unicidad.
        4. Inserta solicitud sintética de enrolamiento local en `camera_pairing_request`
           con estado `'CONSUMIDA'` (auditoría relacional de creador, timestamp e info USB).
        5. Inserta la credencial vinculada en `camara_credencial` con `clave_cifrado_id = 'usb-local-pull'`.
        6. Actualiza `camara.uri_stream = 'usb://<índice>'` dentro de la misma transacción.
        """
        target_uri = f"usb://{int(device_index)}"
        raw_claim = f"vigia_usb_claim_{secrets.token_urlsafe(32)}"
        raw_stream = f"vigia_usb_local_{secrets.token_urlsafe(32)}"
        claim_hash = hash_token_sha256(raw_claim)
        stream_hash = hash_token_sha256(raw_stream)

        conn = self._get_connection()
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # 1. Verificar existencia y bloquear credencial activa previa
                    cur.execute(
                        """
                        SELECT cc.id_credencial, cc.clave_cifrado_id, pr.dispositivo_info
                        FROM camara_credencial cc
                        LEFT JOIN camera_pairing_request pr ON pr.id_solicitud = cc.id_solicitud
                        WHERE cc.id_camara = %s
                          AND cc.activa = TRUE
                        FOR UPDATE OF cc;
                        """,
                        (str(id_camara),),
                    )
                    existing = cur.fetchone()
                    if existing is not None:
                        if not replace_active:
                            ext_info = existing.get("dispositivo_info") or {}
                            ext_name = ext_info.get("nombre") or "Dispositivo activo"
                            raise ActiveCredentialConflictError(
                                f"La cámara '{codigo_camara}' ya tiene un dispositivo activo ('{ext_name}'). "
                                "Confirme explícitamente la sustitución para reemplazarlo.",
                                existing_info={
                                    "id_credencial": str(existing["id_credencial"]),
                                    "clave_cifrado_id": existing["clave_cifrado_id"],
                                    "nombre_dispositivo": ext_name,
                                    "dispositivo_info": ext_info,
                                },
                            )

                        cur.execute(
                            """
                            UPDATE camara_credencial
                            SET activa = FALSE,
                                revocado_por = %s,
                                revocado_en = CURRENT_TIMESTAMP,
                                motivo_revocacion = 'Sustituida explícitamente por cámara USB local'
                            WHERE id_credencial = %s
                              AND activa = TRUE;
                            """,
                            (str(creado_por), str(existing["id_credencial"])),
                        )

                    # 2. Expirar/cancelar solicitudes QR vivas previas para respetar uq_pairing_activa_por_camara
                    cur.execute(
                        """
                        UPDATE camera_pairing_request
                        SET estado = 'CANCELADA',
                            cancelado_en = CURRENT_TIMESTAMP,
                            resuelto_por = %s,
                            motivo_rechazo = 'Cancelada por asignación explícita de cámara USB'
                        WHERE id_camara = %s
                          AND estado IN ('CREADA', 'PENDIENTE');
                        """,
                        (str(creado_por), str(id_camara)),
                    )

                    # 3. Insertar solicitud sintética CONSUMIDA en camera_pairing_request
                    cur.execute(
                        """
                        INSERT INTO camera_pairing_request (
                            id_camara,
                            token_claim_hash,
                            token_poll_hash,
                            estado,
                            dispositivo_info,
                            creado_por,
                            resuelto_por,
                            creado_en,
                            expira_en,
                            reclamado_en,
                            resuelto_en,
                            consumido_en
                        ) VALUES (
                            %s, %s, NULL, 'CONSUMIDA', %s::jsonb,
                            %s, %s,
                            CURRENT_TIMESTAMP,
                            CURRENT_TIMESTAMP + interval '10 minutes',
                            CURRENT_TIMESTAMP,
                            CURRENT_TIMESTAMP,
                            CURRENT_TIMESTAMP
                        )
                        RETURNING *;
                        """,
                        (
                            str(id_camara),
                            claim_hash,
                            json.dumps(dispositivo_info),
                            str(creado_por),
                            str(creado_por),
                        ),
                    )
                    req_row = cur.fetchone()

                    # 4. Insertar credencial USB activa
                    cur.execute(
                        """
                        INSERT INTO camara_credencial (
                            id_camara,
                            id_solicitud,
                            token_transmision_hash,
                            clave_cifrado_id,
                            credencial_cifrada,
                            entregado_en,
                            activa
                        ) VALUES (
                            %s, %s, %s, 'usb-local-pull', NULL, CURRENT_TIMESTAMP, TRUE
                        )
                        RETURNING *;
                        """,
                        (str(id_camara), str(req_row["id_solicitud"]), stream_hash),
                    )
                    cred_row = cur.fetchone()

                    # 5. Actualizar uri_stream de la cámara lógica
                    cur.execute(
                        """
                        UPDATE camara
                        SET uri_stream = %s
                        WHERE id_camara = %s;
                        """,
                        (target_uri, str(id_camara)),
                    )

                    return self._row_to_request_dto(req_row), self._row_to_cred_dto(cred_row)
        except ActiveCredentialConflictError:
            raise
        except Exception as exc:
            raise DatabasePersistenceError(
                f"Error al registrar cámara USB para '{codigo_camara}': {exc}"
            ) from exc
        finally:
            conn.close()

    def get_credential_details(self, id_credencial: UUID) -> Optional[Dict[str, Any]]:
        """Consulta metadatos de una credencial y su cámara lógica asociada."""
        conn = self._get_connection()
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT
                            cc.id_credencial,
                            cc.id_camara,
                            cc.activa,
                            cc.clave_cifrado_id,
                            c.codigo AS codigo_camara,
                            c.nombre AS nombre_camara,
                            c.uri_stream,
                            pr.dispositivo_info
                        FROM camara_credencial cc
                        JOIN camara c ON c.id_camara = cc.id_camara
                        LEFT JOIN camera_pairing_request pr ON pr.id_solicitud = cc.id_solicitud
                        WHERE cc.id_credencial = %s;
                        """,
                        (str(id_credencial),),
                    )
                    row = cur.fetchone()
                    if not row:
                        return None
                    disp_info = row.get("dispositivo_info") or {}
                    is_usb = (
                        row["clave_cifrado_id"] == "usb-local-pull"
                        or str(row["uri_stream"] or "").lower().startswith("usb://")
                        or (isinstance(disp_info, dict) and disp_info.get("modo") == "pull_usb")
                    )
                    return {
                        "id_credencial": UUID(str(row["id_credencial"])),
                        "id_camara": UUID(str(row["id_camara"])),
                        "activa": bool(row["activa"]),
                        "clave_cifrado_id": row["clave_cifrado_id"],
                        "codigo_camara": row["codigo_camara"],
                        "nombre_camara": row["nombre_camara"],
                        "uri_stream": row["uri_stream"],
                        "dispositivo_info": disp_info,
                        "is_usb": is_usb,
                    }
        except Exception as exc:
            raise DatabasePersistenceError(
                f"Error al consultar detalles de credencial: {exc}"
            ) from exc
        finally:
            conn.close()

    def revoke_credential_and_restore_lane(
        self,
        *,
        id_credencial: UUID,
        revocado_por: UUID,
        motivo: str = "Revocación manual desde Dashboard",
    ) -> Optional[Dict[str, Any]]:
        """
        Revoca una credencial activa y, si pertenecía a una cámara USB pull,
        restaura transaccionalmente `camara.uri_stream` al esquema `push://<cam>`.
        Retorna detalles del carril afectado o None si no existe/ya inactiva.
        """
        conn = self._get_connection()
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT
                            cc.id_credencial,
                            cc.id_camara,
                            cc.activa,
                            cc.clave_cifrado_id,
                            c.codigo AS codigo_camara,
                            c.uri_stream,
                            pr.dispositivo_info
                        FROM camara_credencial cc
                        JOIN camara c ON c.id_camara = cc.id_camara
                        LEFT JOIN camera_pairing_request pr ON pr.id_solicitud = cc.id_solicitud
                        WHERE cc.id_credencial = %s
                        FOR UPDATE OF cc;
                        """,
                        (str(id_credencial),),
                    )
                    row = cur.fetchone()
                    if not row or not row["activa"]:
                        return None

                    cur.execute(
                        """
                        UPDATE camara_credencial
                        SET activa = FALSE,
                            revocado_por = %s,
                            revocado_en = CURRENT_TIMESTAMP,
                            motivo_revocacion = %s
                        WHERE id_credencial = %s
                          AND activa = TRUE;
                        """,
                        (str(revocado_por), motivo, str(id_credencial)),
                    )
                    if cur.rowcount == 0:
                        return None

                    disp_info = row.get("dispositivo_info") or {}
                    is_usb = (
                        row["clave_cifrado_id"] == "usb-local-pull"
                        or str(row["uri_stream"] or "").lower().startswith("usb://")
                        or (isinstance(disp_info, dict) and disp_info.get("modo") == "pull_usb")
                    )
                    codigo_cam = str(row["codigo_camara"])
                    restored_uri = f"push://{codigo_cam.lower()}"
                    if is_usb:
                        cur.execute(
                            """
                            UPDATE camara
                            SET uri_stream = %s
                            WHERE id_camara = %s;
                            """,
                            (restored_uri, str(row["id_camara"])),
                        )

                    return {
                        "id_credencial": UUID(str(row["id_credencial"])),
                        "id_camara": UUID(str(row["id_camara"])),
                        "codigo_camara": codigo_cam,
                        "is_usb": is_usb,
                        "restored_uri": restored_uri if is_usb else row["uri_stream"],
                    }
        except Exception as exc:
            raise DatabasePersistenceError(
                f"Error al revocar credencial y restaurar carril: {exc}"
            ) from exc
        finally:
            conn.close()

    def restore_push_uri(self, *, id_camara: UUID, codigo_camara: str) -> str:
        """Restaura `camara.uri_stream` al esquema push://<codigo> cuando vuelve a modo móvil."""
        target_uri = f"push://{codigo_camara.strip().lower()}"
        conn = self._get_connection()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE camara
                        SET uri_stream = %s
                        WHERE id_camara = %s;
                        """,
                        (target_uri, str(id_camara)),
                    )
            return target_uri
        except Exception as exc:
            raise DatabasePersistenceError(
                f"Error al restaurar URI push para '{codigo_camara}': {exc}"
            ) from exc
        finally:
            conn.close()

    def revoke_credential(
        self,
        *,
        id_credencial: UUID,
        revocado_por: UUID,
        motivo: str = "Revocación manual desde Dashboard",
    ) -> bool:
        """Revoca de forma inmediata una credencial de transmisión activa."""
        res = self.revoke_credential_and_restore_lane(
            id_credencial=id_credencial,
            revocado_por=revocado_por,
            motivo=motivo,
        )
        return res is not None

    def validate_stream_token(
        self,
        *,
        codigo_camara: str,
        token_transmision: str,
    ) -> bool:
        """
        Verifica en microsegundos si el token provisto es una credencial móvil individual activa
        para la cámara lógica indicada (excluyendo credenciales USB locales).
        """
        token_hash = hash_token_sha256(token_transmision)
        conn = self._get_connection()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT 1
                        FROM camara_credencial cc
                        JOIN camara c ON c.id_camara = cc.id_camara
                        WHERE c.codigo = %s
                          AND cc.token_transmision_hash = %s
                          AND cc.activa = TRUE
                          AND c.activa = TRUE
                          AND cc.clave_cifrado_id <> 'usb-local-pull'
                        LIMIT 1;
                        """,
                        (codigo_camara, token_hash),
                    )
                    return cur.fetchone() is not None
        except Exception as exc:
            logger.error("Error al validar token de transmisión: %s", exc)
            return False
        finally:
            conn.close()

    def list_active_devices(self) -> List[ActiveDeviceDTO]:
        """Obtiene la lista de dispositivos autorizados activos para el Dashboard."""
        conn = self._get_connection()
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT 
                            cc.id_credencial,
                            cc.id_camara,
                            c.codigo AS codigo_camara,
                            c.nombre AS nombre_camara,
                            COALESCE(pr.dispositivo_info->>'nombre', pr.dispositivo_info->>'device_name', 'Cámara Móvil ' || c.codigo) AS nombre_dispositivo,
                            pr.dispositivo_info,
                            cc.activado_en,
                            cc.activa,
                            (
                                SELECT MAX(fecha_hora) 
                                FROM deteccion d 
                                JOIN area_vision av ON av.id_area_vision = d.id_area_vision 
                                WHERE av.id_camara = c.id_camara
                            ) AS ultima_actividad
                        FROM camara_credencial cc
                        JOIN camara c ON c.id_camara = cc.id_camara
                        LEFT JOIN camera_pairing_request pr ON pr.id_solicitud = cc.id_solicitud
                        ORDER BY cc.activado_en DESC;
                        """
                    )
                    rows = cur.fetchall()
                    result = []
                    for r in rows:
                        result.append(
                            ActiveDeviceDTO(
                                id_credencial=UUID(str(r["id_credencial"])),
                                id_camara=UUID(str(r["id_camara"])),
                                codigo_camara=r["codigo_camara"],
                                nombre_camara=r["nombre_camara"],
                                nombre_dispositivo=r["nombre_dispositivo"],
                                dispositivo_info=r["dispositivo_info"],
                                activado_en=r["activado_en"],
                                activa=bool(r["activa"]),
                                ultima_actividad=r["ultima_actividad"],
                            )
                        )
                    return result
        except Exception as exc:
            raise DatabasePersistenceError(
                f"Error al listar dispositivos activos: {exc}"
            ) from exc
        finally:
            conn.close()

    def get_pending_requests(self) -> List[PairingRequestDTO]:
        """Lista solicitudes pendientes de aprobación para el Dashboard."""
        conn = self._get_connection()
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT * FROM camera_pairing_request
                        WHERE estado = 'PENDIENTE'
                          AND expira_en > CURRENT_TIMESTAMP
                        ORDER BY creado_en ASC;
                        """
                    )
                    return [self._row_to_request_dto(r) for r in cur.fetchall()]
        except Exception as exc:
            raise DatabasePersistenceError(
                f"Error al consultar solicitudes pendientes: {exc}"
            ) from exc
        finally:
            conn.close()

    @staticmethod
    def _row_to_request_dto(row: Any) -> PairingRequestDTO:
        return PairingRequestDTO(
            id_solicitud=UUID(str(row["id_solicitud"])),
            id_camara=UUID(str(row["id_camara"])),
            token_claim_hash=row["token_claim_hash"],
            token_poll_hash=row["token_poll_hash"],
            estado=PairingRequestState(row["estado"]),
            dispositivo_info=row["dispositivo_info"],
            creado_por=UUID(str(row["creado_por"])),
            resuelto_por=UUID(str(row["resuelto_por"])) if row.get("resuelto_por") else None,
            motivo_rechazo=row.get("motivo_rechazo"),
            creado_en=row["creado_en"],
            expira_en=row["expira_en"],
            reclamado_en=row.get("reclamado_en"),
            resuelto_en=row.get("resuelto_en"),
            consumido_en=row.get("consumido_en"),
            cancelado_en=row.get("cancelado_en"),
        )

    @staticmethod
    def _row_to_cred_dto(row: Any) -> CameraCredentialDTO:
        return CameraCredentialDTO(
            id_credencial=UUID(str(row["id_credencial"])),
            id_camara=UUID(str(row["id_camara"])),
            id_solicitud=UUID(str(row["id_solicitud"])),
            token_transmision_hash=row["token_transmision_hash"],
            clave_cifrado_id=row["clave_cifrado_id"],
            credencial_cifrada=row.get("credencial_cifrada"),
            intentos_entrega=row["intentos_entrega"],
            entregado_en=row.get("entregado_en"),
            activa=bool(row["activa"]),
            revocado_por=UUID(str(row["revocado_por"])) if row.get("revocado_por") else None,
            motivo_revocacion=row.get("motivo_revocacion"),
            creado_en=row["creado_en"],
            activado_en=row["activado_en"],
            revocado_en=row.get("revocado_en"),
        )
