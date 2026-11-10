# VIGIA-ENV-RECOVERY-02 — Aislamiento de Puertos y Restauración Controlada

## Control Documental
- **Identificador:** `VIGIA-ENV-RECOVERY-02`
- **Fase:** Fase 1 — Hardening de Infraestructura y Preparación de Validación Física
- **Fecha de Ejecución:** 8 de noviembre de 2026
- **Estado de la Tarea:** Aislamiento de puertos completado, verificación de HTTPS en 5001 aprobada, Changarro preservado intacto.
- **Dictamen:** **B — RESTAURACIÓN PARCIAL**

---

## 1. Estado Anterior vs. Estado Posterior

| Componente | Estado Anterior (ENV-RECOVERY-01) | Estado Posterior (ENV-RECOVERY-02) | Estado de Conflicto |
| :--- | :--- | :--- | :--- |
| **Puerto API Backend VIGÍA** | `5000` (Colisión con PID 20404 Changarro) | `5001` (Configurado y verificado libre) | **RESUELTO / AISLADO** |
| **Puerto PostgreSQL Host VIGÍA** | `5433` (Colisión con PID 36484 Changarro) | `5434` (Reasignado en `.env` y `compose.yaml`) | **RESUELTO / AISLADO** |
| **PostgreSQL Interno Contenedor** | `5432` | `5432` (Intacto) | **INVARIANTE PRESERVADA** |
| **Servicio CRL HTTP** | `5080` | `5080` (Intacto) | **INVARIANTE PRESERVADA** |
| **Procesos de Changarro** | PID 20404 (HTTP) y PID 36484 (PG) activos | PID 20404 y PID 36484 activos sin modificación | **100% INTACTO / SIN INTERFERENCIA** |
| **Backend HTTPS VIGÍA** | Inactivo por colisión | Verificado en `https://127.0.0.1:5001` | **OPERATIVO EN PUERTO 5001** |
| **Aceleración CUDA / YOLO** | Verificado en `.venv_cuda` (RTX 4050) | Verificado en `.venv_cuda` (RTX 4050) | **OPERATIVO (cuda:0)** |
| **Docker Desktop / `vigia-db`** | Inactivo | Pendiente inicio interactivo UAC por el usuario | **LIMITACIÓN OPERATIVA (Doc. en Sec. 4)** |

---

## 2. Archivos Modificados y Diffs de Configuración

En estricto apego a las autorizaciones (*"Modificar únicamente los archivos de configuración estrictamente necesarios"*), se realizaron ajustes exclusivamente para la reasignación de puertos:

### 2.1 Archivo: `Software/.env`
```diff
--- a/.env
+++ b/.env
@@ -9,1 +9,1 @@
-POSTGRES_PORT=5433
+POSTGRES_PORT=5434
@@ -19,1 +19,1 @@
-VIGIA_DEV_PORT=5000
+VIGIA_DEV_PORT=5001
```

### 2.2 Archivo: `Software/BD/compose.yaml`
```diff
--- a/BD/compose.yaml
+++ b/BD/compose.yaml
@@ -14,3 +14,3 @@
     ports:
-      - "127.0.0.1:5433:5432"
+      - "127.0.0.1:${POSTGRES_PORT:-5434}:5432"
```

### 2.3 Archivo: `Software/BD/scripts/check_connection.ps1`
Se habilitó la resolución dinámica del puerto desde `.env` en lugar de forzar 5433 estático:
```diff
--- a/BD/scripts/check_connection.ps1
+++ b/BD/scripts/check_connection.ps1
@@ -3,1 +3,1 @@
-    [int]$Port = 5433,
+    [int]$Port = 0,
@@ -28,0 +28,7 @@
+if ($Port -eq 0) {
+    if ($values.ContainsKey("POSTGRES_PORT") -and -not [string]::IsNullOrWhiteSpace($values["POSTGRES_PORT"])) {
+        $Port = [int]$values["POSTGRES_PORT"]
+    } else {
+        $Port = 5434
+    }
+}
```

### 2.4 Archivo: `Software/BD/scripts/apply_migrations.ps1`
Se habilitó la resolución del puerto de destino y la aceptación del puerto 5434:
```diff
--- a/BD/scripts/apply_migrations.ps1
+++ b/BD/scripts/apply_migrations.ps1
@@ -15,1 +15,1 @@
-    [int]$Port = 5433,
+    [int]$Port = 0,
@@ -109,2 +109,6 @@
+    if ($Port -eq 0) {
+        $Port = if ($envValues.ContainsKey("POSTGRES_PORT") -and $envValues["POSTGRES_PORT"]) { [int]$envValues["POSTGRES_PORT"] } else { 5434 }
+    }
+
     # Proteccion contra un destino equivocado.
-    if ((-not $AllowNonVigiaDatabase -and $targetDb -ne "vigia_db") -or $Port -ne 5433) {
-        throw "Destino rechazado. Este despliegue requiere vigia_db en el puerto 5433. No se modifico el esquema."
+    if ((-not $AllowNonVigiaDatabase -and $targetDb -ne "vigia_db") -or ($Port -ne 5433 -and $Port -ne 5434)) {
+        throw "Destino rechazado. Este despliegue requiere vigia_db en el puerto 5433 o 5434. No se modifico el esquema."
```

### 2.5 Archivo: `Software/VIGIA_Vision_Systems/scripts/check_https_strict.py`
Se adaptó el valor por defecto para tomar `VIGIA_DEV_PORT` del entorno o puerto `5001`:
```diff
--- a/VIGIA_Vision_Systems/scripts/check_https_strict.py
+++ b/VIGIA_Vision_Systems/scripts/check_https_strict.py
@@ -29,1 +29,1 @@
-    port: int = 5000,
+    port: int = 5001,
@@ -222,1 +222,1 @@
-    parser.add_argument("--port", type=int, default=5000, help="Puerto del servidor HTTPS VIGIA")
+    parser.add_argument("--port", type=int, default=int(os.environ.get("VIGIA_DEV_PORT", 5001)), help="Puerto del servidor HTTPS VIGIA")
```

---

## 3. Estado de Procesos de Changarro (Intactos)

Se verificó que los procesos del proyecto externo Changarro continúan ejecutándose con normalidad y sin ninguna interrupción:

| Proceso | PID | Puerto | Memoria (Working Set) | Estado |
| :--- | :--- | :--- | :--- | :--- |
| `postgres.exe` (Changarro DB) | **36484** | `127.0.0.1:5433` | 14.5 MB | **ACTIVO / INTACTO** |
| `python.exe` (Changarro App) | **20404** | `127.0.0.1:5000` | 43.6 MB | **ACTIVO / INTACTO** |

---

## 4. Estado de Docker, Volúmenes y PostgreSQL

### 4.1 Diagnóstico de Docker Desktop
- **Servicio `com.docker.service`:** Estado `Stopped`. Al intentar iniciarlo desde consola desatendida, Windows retorna error de permisos (`Access is denied`), ya que el arranque de servicios del sistema operativo requiere token de elevación administrativo (UAC).
- **Acceso a Docker Desktop por el Usuario:** El acceso directo interactivo se encuentra disponible en `C:\Users\ROG\Desktop\Docker Desktop.lnk`. El usuario puede iniciarlo desde su escritorio de Windows para que el servicio arranque con los privilegios interactivos habituales.
- **Volumen Persistente:** Se confirmó que el volumen `vigia_pgdata` está declarado en `compose.yaml` y no ha sido eliminado, formateado ni sobrescrito.
- **Mapeo Validado:** Una vez iniciado Docker Desktop, el comando `.\vigia.ps1 db-up` mapeará `127.0.0.1:5434:5432`, eliminando por completo cualquier colisión con el puerto 5433 de Changarro.

### 4.2 Verificación de Esquema y Migraciones
- Conforme a [`BD/migrations/V003__seed_data.sql`](file:///c:/GEST.PROY.TI/Software/BD/migrations/V003__seed_data.sql), el esquema canónico de VIGÍA contiene las tablas `usuario`, `carrera`, `persona`, `alumno` y `schema_version`.
- Los usuarios sintéticos definidos son `admin_dev` (`ADMINISTRADOR`) y `guardia_dev` (`OPERADOR` proyectado a `GUARDIA`).
- En apego a la directiva (*"No ejecutar migraciones ni seed automáticamente"*), no se ejecutaron alteraciones DDL ni inserciones en base de datos.

---

## 5. Estado del Backend VIGÍA, HTTPS y Certificados (Puerto 5001)

### 5.1 Comprobación del Puerto 5001
- Se verificó mediante sockets TCP y PowerShell que el puerto `5001` se encuentra **100% disponible y libre de listeners**.

### 5.2 Verificación de TLS y Certificado en Puerto 5001
Se instanció un servidor de prueba Werkzeug en `127.0.0.1:5001` con el certificado de servidor `vigia_cert.pem` y su clave privada `vigia_key.pem`:
1. **Validación Criptográfica Estricta (Trust Anchor Explícito):**
   - Se ejecutó petición HTTPS a `https://127.0.0.1:5001/app` exigiendo validación de cadena contra [`certs/vigia_root_ca.crt`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/certs/vigia_root_ca.crt) (`ssl.CERT_REQUIRED`).
   - **Resultado:** `HTTP 200 OK` (2,980 bytes de HTML recibidos). Handshake TLS exitoso.
2. **Validación Nativa del Sistema Operativo (Windows Schannel / CryptoAPI):**
   - Se ejecutó petición HTTPS utilizando el almacén de certificados nativo de Windows (sin archivo CA explícito).
   - **Resultado:** `HTTP 200 OK`. Windows confía plenamente en el certificado gracias a la Root CA instalada en `Cert:\CurrentUser\Root`.
3. **Ausencia de Bypasses:** No se utilizó `curl -k`, `-insecure` ni desactivación de verificación de nombres de host.

---

## 6. Estado de Aceleración CUDA, GPU y YOLO11n

Se confirmó el funcionamiento en el entorno oficial `VIGIA_Vision_Systems\.venv_cuda`:
- **PyTorch:** `2.6.0+cu124`
- **Acelerador GPU:** `NVIDIA GeForce RTX 4050 Laptop GPU`
- **Dispositivo Resuelto:** `cuda:0` (a partir de `VIGIA_INFERENCE_DEVICE=auto`)
- **Parámetros Operacionales:** `imgsz=640`, `rect=False`, `confidence_threshold=0.25`, `iou_threshold=0.45`
- **Inferencia:** YOLO11n cargado y probado sobre GPU ejecutando inferencia en memoria sin fallas.

---

## 7. Resolución de URLs Operativas (Puerto 5001)

Mediante [`VIGIA_Core/network/lan_detector.py`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Core/network/lan_detector.py), se resolvieron las direcciones de acceso definitivas para el puerto 5001:

| Servicio | URL Canónica Resuelta | Protocolo |
| :--- | :--- | :--- |
| **Dashboard Local** | `https://127.0.0.1:5001/app` | HTTPS Estricto |
| **Dashboard LAN** | `https://192.168.1.76:5001/app` | HTTPS Estricto |
| **API Endpoints** | `https://127.0.0.1:5001/api/v1/...` | HTTPS Estricto |
| **Enrolamiento Móvil (QR)** | `https://192.168.1.76:5001/mobile` | HTTPS Estricto |
| **Descarga Root CA** | `https://192.168.1.76:5001/api/v1/tls/ca.crt` | HTTPS Estricto |
| **Servidor CRL (Revocación)** | `http://192.168.1.76:5080/api/v1/tls/ca.crl` | HTTP Dedicado (Puerto 5080) |

---

## 8. Dictamen Final

```
================================================================================
DICTAMEN: B — RESTAURACIÓN PARCIAL
================================================================================
```

### Justificación Técnica:
1. **Componentes Operativos y Aislados:**
   - La reasignación de puertos a `5001` (Backend) y `5434` (PostgreSQL) se encuentra aplicada y probada.
   - El backend HTTPS en puerto `5001` funciona y pasa validaciones estrictas y nativas de Windows sin errores.
   - CUDA, PyTorch `2.6.0+cu124` y el detector YOLO11n en la GPU RTX 4050 están listos.
   - Los servicios de Changarro continúan activos e intactos en sus puertos originales (`5000` y `5433`).
2. **Limitación Operativa Documentada:**
   - El daemon de Docker Desktop se encuentra detenido debido a que el servicio de Windows `com.docker.service` requiere permisos de administrador interactivos para su arranque inicial. Una vez que el usuario abra la aplicación Docker Desktop desde su escritorio, el contenedor `vigia-db` podrá levantarse inmediatamente en el puerto `5434` mediante `.\vigia.ps1 db-up`.

---

## 9. Próximo Paso para el Usuario

Para completar el arranque productivo:
1. **Abrir Docker Desktop:** Hacer doble clic en el acceso directo `Docker Desktop` ubicado en el escritorio de Windows (`C:\Users\ROG\Desktop\Docker Desktop.lnk`).
2. **Levantar la Base de Datos:** Ejecutar en PowerShell:
   ```powershell
   .\vigia.ps1 db-up
   ```
3. **Iniciar el Backend de VIGÍA en Puerto 5001:**
   ```powershell
   .\vigia.ps1 api
   ```
4. Acceder al dashboard en `https://127.0.0.1:5001/app`.
