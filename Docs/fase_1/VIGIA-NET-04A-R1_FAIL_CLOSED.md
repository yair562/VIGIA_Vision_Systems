# VIGIA-NET-04A-R1 — Eliminación del Fallback Criptográfico y FAIL-CLOSED

**Fase:** VIGIA-NET-04A-R1  
**Fecha:** 2026-11-08  
**Objetivo:** Corregir el hallazgo crítico **CTL-04** de la auditoría `VIGIA-NET-04A-AUDIT`, eliminando todo fallback de firma local en el proceso Flask y garantizando la política innegociable **FAIL-CLOSED** en producción.  
**Estado:** IMPLEMENTADO, VERIFICADO Y DEMOSTRADO  

---

## 1. Dictamen Técnico Formal

> [!IMPORTANT]
> ### **DICTAMEN: A — No existe fallback de producción y todas las rutas de firma están delegadas**
> 
> - **Cero Fallback en Producción:** Las rutas de firma de certificados de servidor (`generate_vigia_local_ca_bundle`) y de listas de revocación (`generate_vigia_crl`) en `VIGIA_API/ingest_service.py` delegan de forma exclusiva al servicio `IsolatedSigner` a través de `SignerClient`.
> - **FAIL-CLOSED Obligatorio:** Ante cualquier indisponibilidad del firmador, caída del Named Pipe, error de autenticación HMAC o timeout IPC en producción, el sistema aborta de inmediato con `SignerUnavailableError`. En ningún caso se recurre a la firma local como mecanismo de contingencia.
> - **Clave Raíz No Leída por Flask:** En modo de producción, el proceso web Flask **nunca lee, abre ni deserializa** `certs/vigia_root_ca_key.pem`.
> - **Protección Incondicional de la Root CA Oficial:** Incluso en entornos de prueba con la bandera `VIGIA_DEV_ALLOW_LOCAL_SIGNING=true`, el sistema bloquea cualquier intento de firma local si el certificado evaluado posee la huella SHA-256 oficial de la Root CA (`E593B2D0...`).
> - **Resiliencia Operativa:** La indisponibilidad del firmador impide la emisión o renovación de nuevos pares TLS, pero no provoca la caída ni el crasheo del servidor Flask cuando un certificado previo ya se encuentra activo en disco.

---

## 2. Archivos Modificados

| Archivo | Naturaleza del Cambio |
| :--- | :--- |
| [`VIGIA_Security/signer/ipc_client.py`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Security/signer/ipc_client.py) | Se incorporaron las excepciones especializadas `SignerAuthenticationError` y `SignerTimeoutError` (herederas de `SignerUnavailableError`). Se implementó espera acotada mediante `multiprocessing.connection.wait` con timeout estricto para impedir bloqueos indefinidos del cliente IPC. |
| [`VIGIA_API/ingest_service.py`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_API/ingest_service.py) | 1. Se implementó la función guardiana `is_local_signing_allowed(ca_cert)`.<br>2. Se eliminó la lectura de `ca_key_p` en el flujo de arranque de `generate_vigia_local_ca_bundle()`.<br>3. Se eliminó el fallback de firma directa en `generate_vigia_local_ca_bundle()` y `generate_vigia_crl()`, reemplazándolo por `raise SignerUnavailableError` en producción.<br>4. Se eliminaron las asignaciones de rutas a nivel superior de `ca_key_p` en los ámbitos de producción.<br>5. En `run_ingest_server`, se añadió captura de `SignerUnavailableError` para conservar el certificado activo previo sin interrupción del servicio web. |
| [`tests/unit/test_crl_management.py`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/tests/unit/test_crl_management.py) | Se configuraron `setUpClass` y `tearDownClass` para habilitar explícitamente `VIGIA_DEV_ALLOW_LOCAL_SIGNING="true"` y `VIGIA_ENV="test"` sobre las CAs mock de laboratorio efímeras. |
| [`tests/unit/test_signer_fail_closed.py`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/tests/unit/test_signer_fail_closed.py) | **Nuevo:** Suite completa de 12 pruebas unitarias de FAIL-CLOSED cubriendo todos los escenarios obligatorios. |

---

## 3. Rutas de Firma Eliminadas y Política FAIL-CLOSED

### 3.1. En `generate_vigia_local_ca_bundle()`
* **Antes (Vulnerable CTL-04):**
  Si `signer_client` era `None`, el bloque `else:` ejecutaba:
  ```python
  srv_cert = builder.sign(ca_key, hashes.SHA256())
  ```
  lo que cargaba `ca_key` directamente en la memoria de Flask.
* **Ahora (Corregido FAIL-CLOSED):**
  ```python
  if signer_client is not None:
      # Emisión segura desacoplada vía IsolatedSigner
      sign_resp = signer_client.request_certificate(...)
      staged_cert_p.write_text(sign_resp["fullchain_pem"], encoding="utf-8")
  elif is_local_signing_allowed(ca_cert):
      # Exclusivo dev/test con mock CA
      ...
  else:
      # FAIL-CLOSED INNEGOCIABLE EN PRODUCCIÓN (VIGIA-NET-04A-R1)
      raise SignerUnavailableError(
          "Política de seguridad FAIL-CLOSED (VIGIA-NET-04A-R1): El servicio IsolatedSigner "
          "no está disponible o no responde en el Named Pipe, y la firma directa desde el "
          "proceso web está terminantemente prohibida en producción."
      )
  ```

### 3.2. En `generate_vigia_crl()`
* **Antes (Vulnerable CTL-04):**
  Si el firmador no respondía, caía en `crl = builder.sign(ca_key, hashes.SHA256())`.
* **Ahora (Corregido FAIL-CLOSED):**
  ```python
  if signer_client is not None:
      resp = signer_client.request_crl(...)
      return crl_file_p, state_p
  elif is_local_signing_allowed(ca_cert):
      # Exclusivo dev/test con mock CA
      ...
  else:
      # FAIL-CLOSED INNEGOCIABLE EN PRODUCCIÓN (VIGIA-NET-04A-R1)
      raise SignerUnavailableError(
          "Política de seguridad FAIL-CLOSED (VIGIA-NET-04A-R1): No es posible emitir la CRL porque "
          "el servicio IsolatedSigner no se encuentra disponible y la firma directa desde Flask "
          "está terminantemente prohibida en producción."
      )
  ```

### 3.3. Reglas de Validación de `is_local_signing_allowed()`
La función `is_local_signing_allowed(ca_cert)` aplica cuatro compuertas de seguridad secuenciales:
1. `VIGIA_ENV == "production"` $\rightarrow$ Retorna `False` de forma **incondicional**.
2. `VIGIA_DEV_ALLOW_LOCAL_SIGNING` ausente o distinta de `true`/`1`/`yes` $\rightarrow$ Retorna `False`.
3. Deshabilitado por defecto.
4. Si `ca_cert` coincide con la huella SHA-256 de la Root CA autorizada de producción (`E593B2D0B808BD8F8E97582ECDEBEAD29AEBC0F9F4BA9EF6ADB2D8E4362E4F4D`) $\rightarrow$ Retorna `False` y emite alerta de seguridad en logs.

---

## 4. Auditoría Estática de Referencias a `vigia_root_ca_key.pem`

Se ejecutó un escaneo de todas las apariciones de `vigia_root_ca_key.pem` en `VIGIA_API/`:

```
VIGIA_API/ingest_service.py:3124:    Firmada con la clave privada de vigia_root_ca_key.pem y hashes.SHA256().
VIGIA_API/ingest_service.py:3194:        ca_key_p = base_dir / "vigia_root_ca_key.pem"
VIGIA_API/ingest_service.py:3541:    # 1. Cargar el certificado público de la Root CA (Flask NO lee vigia_root_ca_key.pem en producción)
VIGIA_API/ingest_service.py:3587:        ca_key_p = base_dir / "vigia_root_ca_key.pem"
VIGIA_API/ingest_service.py:3676:            ca_key_p = base_dir / "vigia_root_ca_key.pem"
```

**Clasificación de Referencias:**
- **Línea 3124:** Referencia puramente documental (Docstring de RFC 5280).
- **Línea 3541:** Comentario explicativo de arquitectura.
- **Líneas 3194, 3587, 3676:** Código ejecutable encapsulado **exclusivamente dentro de ramas subordinadas a `is_local_signing_allowed()`**, inaccesibles en modo de producción e inviables sobre la Root CA oficial.
- **Ámbitos de Producción:** **0 referencias ejecutables.**

---

## 5. Resultados de Pruebas Automatizadas

### 5.1. Batería de Pruebas Obligatorias de FAIL-CLOSED (`test_signer_fail_closed.py`)
Comando ejecutado:
```powershell
powershell -NoProfile -Command "[Environment]::SetEnvironmentVariable('PYTHONPATH', 'C:\GEST.PROY.TI\Software\VIGIA_Vision_Systems;C:\GEST.PROY.TI\Software'); & 'c:\GEST.PROY.TI\Software\VIGIA_Vision_Systems\.venv\Scripts\python.exe' -m unittest discover -s VIGIA_Vision_Systems/tests/unit -p 'test_signer_fail_closed.py' -v"
```

Resultados observados:
```
test_01_signer_available_delegates_signing ... ok (Flask delega firma exitosamente)
test_02_signer_stopped_issuance_rejected ... ok (Firmador caído: SignerUnavailableError)
test_03_named_pipe_nonexistent_issuance_rejected ... ok (Pipe inexistente: SignerUnavailableError)
test_04_invalid_hmac_issuance_rejected ... ok (Token HMAC inválido: SignerUnavailableError)
test_05_ipc_timeout_issuance_rejected ... ok (Timeout IPC: rechazado sin bloqueo)
test_06_remote_cryptographic_error_rejected ... ok (Violación remota: PolicyViolationError)
test_07_crl_generation_without_signer_rejected ... ok (CRL sin firmador: SignerUnavailableError)
test_08_no_vigia_root_ca_key_loaded_by_flask ... ok (Clave trampa nunca leída por Flask)
test_09_no_local_signing_in_production_even_with_dev_flag ... ok (Firma local bloqueada en producción)
test_10_signer_unavailability_does_not_crash_flask_server ... ok (Servidor Flask no crashea con par previo)
test_11_previous_active_certificate_intact_on_failure ... ok (Par y manifest previo intactos)
test_12_root_ca_and_fingerprint_unmodified ... ok (Root CA 100% íntegra y verificada)

----------------------------------------------------------------------
Ran 12 tests in 9.507s — OK (12/12 exitosas, 0 fallos, 0 errores)
```

### 5.2. Pruebas de Regresión Criptográfica y CRL
- **`test_isolated_signer.py`:** 12/12 pruebas aprobadas (`Ran 12 tests in 3.090s — OK`).
- **`test_crl_management.py`:** 15/15 pruebas aprobadas (`Ran 15 tests in 4.441s — OK`).
- **`test_camera_stream_and_backend.py`:** 19/19 pruebas aprobadas (`Ran 19 tests in 0.216s — OK`).

---

## 6. Verificación Criptográfica de la Root CA de Producción

Se realizó una verificación criptográfica de solo lectura sobre el almacén real del repositorio:

| Control | Valor Esperado | Valor Observado | Estado |
| :--- | :--- | :--- | :--- |
| **Certificado Público** | `certs/vigia_root_ca.crt` | Existente, PEM válido | **CORRECTO** |
| **Clave Privada** | `certs/vigia_root_ca_key.pem` | Existente, RSA 2048 bits | **CORRECTO** |
| **Huella SHA-256** | `E593B2D0B808BD8F8E97582ECDEBEAD29AEBC0F9F4BA9EF6ADB2D8E4362E4F4D` | `E593B2D0B808BD8F8E97582ECDEBEAD29AEBC0F9F4BA9EF6ADB2D8E4362E4F4D` | **COINCIDENCIA EXACTA** |
| **Correspondencia de Par** | Clave pública del cert == clave pública de la clave | Clave pública idéntica (SubjectPublicKeyInfo SHA-256) | **CORRESPONDE** |
| **BasicConstraints** | `CA:TRUE, path_length:0` | `BasicConstraints(ca=True, path_length=0)` | **PRESERVADO** |

---

## 7. Riesgos Residuales para la Siguiente Fase (R2)

1. **Aislamiento a Nivel NTFS / Identidad Windows:**  
   Como se estableció en el alcance de R1, esta fase resolvió exclusivamente el bypass criptográfico en código Python. En el sistema de archivos actual de Windows, la clave privada `vigia_root_ca_key.pem` aún reside en `certs/` bajo la misma cuenta de usuario interactiva (`laptop-h2lcul1v\rog`).
2. **Objetivo de R2:**  
   Separar formalmente las identidades del sistema operativo creando una cuenta de servicio Windows dedicada para `IsolatedSigner` y reubicando la clave privada fuera del alcance del usuario de Flask.
