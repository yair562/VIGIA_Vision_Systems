# VIGIA-ENV-RECOVERY-01 — Diagnóstico y Recuperación Controlada del Entorno de Pruebas

## Control Documental
- **Identificador:** `VIGIA-ENV-RECOVERY-01`
- **Fase:** Fase 1 — Hardening de Infraestructura y Preparación de Validación Física
- **Fecha de Auditoría:** 8 de noviembre de 2026
- **Naturaleza de la Actividad:** Diagnóstico pasivo y no invasivo de infraestructura (Solo lectura; sin modificación de código, configuraciones, `.env` ni certificados; sin terminación de procesos externos)
- **Dictamen:** **C. BLOQUEADO**

---

## 1. Estado Inicial del Entorno

La auditoría previa de la prueba de transmisiones ([`Docs/fase_1/VIGIA-AUTH-01-PHYSICAL-VERIFICATION.md`](file:///c:/GEST.PROY.TI/Software/Docs/fase_1/VIGIA-AUTH-01-PHYSICAL-VERIFICATION.md)) evidenció que el backend de VIGÍA y su base de datos PostgreSQL no estaban activos en los puertos estándar, obligando a ejecutar las verificaciones mediante arneses en memoria.

Para posibilitar una validación física real en caseta con sockets TCP, navegador gráfico y dispositivos móviles, se realizó una inspección exhaustiva de los puertos, procesos, Docker, aceleración CUDA y certificados TLS.

---

## 2. Diagnóstico de Procesos y Puertos (Fase A)

### 2.1 Inspección del Puerto TCP 5000 (Backend VIGÍA)
- **Estado de Escucha:** Puerto ocupado en `127.0.0.1:5000`.
- **Proceso Propietario:** `python.exe` (PID: **20404**).
- **Ruta del Ejecutable:** `C:\Python314\python.exe`
- **Línea de Comandos Completa:** `"C:\Chamba\Changarro\Changarro_App\backend\venv\Scripts\python.exe" run.py`
- **Hora de Inicio del Proceso:** 08/11/2026 10:35:56 AM.
- **Proyecto Perteneciente:** Proyecto externo **Changarro** (`C:\Chamba\Changarro`).
- **Respuesta HTTP:** Devuelve `HTTP 404 NOT FOUND` en peticiones HTTP planas sin cifrar. No cuenta con TLS/HTTPS de VIGÍA.
- **Acción Tomada:** En cumplimiento estricto de las restricciones (*"NO detener ni modificar servicios de otros proyectos. NO liberar puertos terminando procesos desconocidos"*), el proceso 20404 **no fue terminado ni alterado**.

### 2.2 Inspección del Puerto TCP 5433 (PostgreSQL VIGÍA)
- **Estado de Escucha:** Puerto ocupado en `127.0.0.1:5433`.
- **Proceso Propietario:** `postgres.exe` (PID: **36484**).
- **Ruta del Ejecutable:** `C:\Program Files\PostgreSQL\18\bin\postgres.exe`
- **Línea de Comandos Completa:** `"C:\Program Files\PostgreSQL\18\bin\postgres.exe" -D C:\Chamba\Changarro\.pgdata -p 5433`
- **Hora de Inicio del Proceso:** 08/11/2026 09:58:58 AM.
- **Proyecto Perteneciente:** Proyecto externo **Changarro** (`C:\Chamba\Changarro\.pgdata`).
- **Verificación Relacional:** El sondeo con el usuario `vigia_admin` falló con: `psql: error: FATAL: role "vigia_admin" does not exist`.

### 2.3 Análisis de Impacto de Puertos Alternativos para VIGÍA
Dado que los puertos configurados en `Software/.env` (`VIGIA_DEV_PORT=5000` y `POSTGRES_PORT=5433`) están ocupados por Changarro, se evaluó técnicamente el impacto de utilizar puertos alternativos (ej. `5001` para API y `5434` para PostgreSQL):

| Componente | Comportamiento ante Cambio de Puerto | Nivel de Impacto |
| :--- | :--- | :--- |
| **Certificados TLS (X.509 / SAN)** | Los certificados digitales RFC 5280 vinculan criptográficamente identidades de host (FQDN) e IPs (`localhost`, `127.0.0.1`, `10.159.253.185`). **La extensión SAN no incluye números de puerto.** El certificado activo `vigia_cert.pem` seguirá siendo 100% válido en cualquier puerto. | **NULO (Sin afectación criptográfica)** |
| **Punto de Distribución CRL (CDP)** | El certificado contiene `http://10.159.253.185:5080/api/v1/tls/ca.crl`. Utiliza el puerto dedicado `5080`, independiente del puerto del API. | **NULO** |
| **Dashboard Web (`api-service.js`)** | [`resolveApiBaseUrl()`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Dashboard/web/js/services/api-service.js#L35) utiliza rutas relativas (`/api/v1/...`). Al acceder a `https://<host>:<puerto>/app`, el navegador resuelve automáticamente las peticiones al mismo puerto de origen. | **NULO** |
| **URLs Móviles y Códigos QR** | [`lan_detector.py`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Core/network/lan_detector.py#L546) lee dinámicamente `VIGIA_DEV_PORT` del entorno para ensamblar las URLs del QR. Se actualizaría automáticamente si se modificara el `.env`. | **BAJO (Requiere sincronización de `.env`)** |
| **PostgreSQL Docker (`compose.yaml`)** | Consume `${POSTGRES_PORT}:5432`. Reasignar a `5434:5432` evitaría colisión con Changarro sin afectar el contenedor interno. | **MEDIO (Requiere autorización de `.env`)** |

*Nota:* En cumplimiento de las instrucciones (*"IMPORTANTE: no cambiar el puerto de VIGÍA todavía"*), **no se ha modificado ningún puerto ni variable en `.env`**.

---

## 3. Diagnóstico de Docker y PostgreSQL (Fase B y C)

### 3.1 Estado de Docker Desktop
- **Servicio de Windows (`com.docker.service`):** Estado `Stopped`.
- **Motor Docker (Linux Engine):** Inactivo. El socket/pipe `//./pipe/dockerDesktopLinuxEngine` no responde (`The system cannot find the file specified`).
- **Contenedores y Volúmenes:** Inaccesibles mientras el daemon de Docker Desktop esté apagado.

### 3.2 Especificación de Infraestructura en [`BD/compose.yaml`](file:///c:/GEST.PROY.TI/Software/BD/compose.yaml)
- **Servicio:** `db` (`image: postgres:16-alpine`, `container_name: vigia-db`)
- **Variables de Entorno Requeridas:** `POSTGRES_DB=vigia_db`, `POSTGRES_USER=vigia_admin`, `POSTGRES_PASSWORD`
- **Mapeo de Puertos:** `"127.0.0.1:5433:5432"` (Actualmente colisiona con PID 36484 de Changarro).
- **Volumen Persistente:** `vigia_pgdata` (`/var/lib/postgresql/data`).

### 3.3 Procedimiento Seguro para Iniciar Docker Desktop (Sin Acciones Destructivas)
Para cuando se cuente con autorización:
1. Iniciar la aplicación Docker Desktop desde Windows (`C:\Program Files\Docker\Docker\Docker Desktop.exe`) o iniciar el servicio `com.docker.service` vía PowerShell administrativo (`Start-Service com.docker.service`).
2. Esperar a que el comando `docker info` responda exitosamente confirmando que el motor Linux está operativo.
3. **No ejecutar `docker compose down -v`** bajo ninguna circunstancia para proteger el volumen `vigia_pgdata`.
4. Resolver la colisión del puerto 5433 antes de invocar `.\vigia.ps1 db-up`.

---

## 4. Diagnóstico del Backend VIGÍA (Fase D)

### 4.1 Inspección del Launcher Oficial [`Software/vigia.ps1`](file:///c:/GEST.PROY.TI/Software/vigia.ps1)
- **Comandos Soportados:** `db-up`, `db-down`, `db-check`, `db-migrate`, `topology`, `api`, `net-check`, `trust-ca`, `verify-ca`, `untrust-ca`, `check-tls`.
- **Selección de Entorno:**
  - Detecta automáticamente el entorno con aceleración por GPU (`VIGIA_Vision_Systems\.venv_cuda\Scripts\python.exe`).
  - Evalúa la variable `VIGIA_INFERENCE_DEVICE` (configurada en `auto` en `Software/.env`).
- **Comando de Arranque del Backend:**
  ```powershell
  Set-Location $root; $env:PYTHONPATH = Join-Path $root "VIGIA_Vision_Systems"; & $py -m VIGIA_API.ingest_service
  ```
- **Condición Actual de Bloqueo:** No se puede ejecutar `.\vigia.ps1 api` debido a que el puerto TCP 5000 está ocupado por Changarro (PID 20404) y el puerto de base de datos 5433 está ocupado por la instancia ajena de PostgreSQL (PID 36484).

---

## 5. Diagnóstico de CUDA, GPU y Modelo YOLO (Fase D)

Se verificó el entorno especializado `VIGIA_Vision_Systems/.venv_cuda` con resultados 100% satisfactorios:

```text
=== TORCH / CUDA CHECK ===
PyTorch version: 2.6.0+cu124
CUDA available: True
Device count: 1
Device 0: NVIDIA GeForce RTX 4050 Laptop GPU

=== YOLO DETECTOR CHECK ===
VIGIA_INFERENCE_DEVICE in env: auto
Resolved inference device: cuda:0
Config: YoloDetectorConfig(model_path='yolo11n.pt', confidence_threshold=0.25, device='cuda:0', imgsz=640, iou_threshold=0.45, classes=(2, 3, 5, 7))
Loading model weights: yolo11n.pt
Model loaded successfully: YOLO (Ultralytics)
Inference on 640x480 dummy image: SUCCESSFUL (cuda:0)
Effective device: cuda:0
```

- **Versión de PyTorch:** `2.6.0+cu124` (con soporte para compute capability de arquitectura Ada Lovelace / sm_89).
- **Acelerador de Hardware:** `NVIDIA GeForce RTX 4050 Laptop GPU` operativa.
- **Configuración de Inferencia:** `VIGIA_INFERENCE_DEVICE=auto` $\rightarrow$ resuelto a `cuda:0`.
- **Resolución de Inferencia:** `imgsz=640` con `rect=False` (configuración estándar unificada).
- **Modelo:** Ultralytics YOLO11n cargado y validado mediante inferencia en GPU.

---

## 6. Diagnóstico de HTTPS, Certificados y PKI (Fase E)

Se auditó la cadena criptográfica completa conforme al estándar estricto de VIGÍA:

### 6.1 Root CA Ancla
- **Ubicación:** `C:\GEST.PROY.TI\Software\VIGIA_Vision_Systems\certs\vigia_root_ca.crt`
- **Sujeto / Emisor:** `CN=VIGIA Local Root CA, OU=Seguridad e Infraestructura LAN, O=VIGIA Vision Systems, C=MX`
- **Huella Digital SHA-256:** `E593B2D0B808BD8F8E97582ECDEBEAD29AEBC0F9F4BA9EF6ADB2D8E4362E4F4D`
- **Validez:** 01/11/2026 hasta 29/10/2036 (Vigente).
- **Almacén de Windows:** Verificado mediante `.\vigia.ps1 verify-ca` en `Cert:\CurrentUser\Root`. **Estado: [OK] INSTALADO Y CONFIABLE**.

### 6.2 Certificado Activo de Servidor
- **Archivo de Metadatos:** `certs/active_generation.json` (`generation_id: gen_20261106_192120_e58052da`).
- **Certificado:** `certs/vigia_cert.pem`
- **Sujeto:** `CN=VIGIA LAN Server (10.159.253.185), O=VIGIA Vision Systems, C=MX`
- **Emisor:** `CN=VIGIA Local Root CA`
- **Validez:** 06/11/2026 hasta 04/02/2027 (**Vigente**).
- **Nombres Alternativos del Sujeto (SAN):**
  - DNS: `localhost`
  - IP: `127.0.0.1`
  - IP: `10.159.253.185`
- **Punto de Distribución de Listas de Revocación (CDP):**
  - `http://10.159.253.185:5080/api/v1/tls/ca.crl` (Puerto CRL: 5080).
- **Diagnóstico TLS:** La infraestructura de certificados se encuentra íntegra, matemáticamente validada y reconocida por Windows Schannel y CryptoAPI.

---

## 7. Cambios Realizados

**NINGUNO.**
En cumplimiento estricto de la regla final y directrices de solo lectura:
- No se modificó código Python, JavaScript, CSS ni HTML.
- No se modificó el archivo `Software/.env` ni variables del sistema.
- No se alteraron migraciones, esquemas ni seed data.
- No se terminaron procesos del sistema (PID 20404 y PID 36484 permanecen intactos).
- No se regeneraron certificados ni se alteró el trust store de Windows.

---

## 8. Matriz de Riesgos y Bloqueos de Infraestructura

| Bloqueo | Descripción del Conflicto | Riesgo si se Forzara Acción Sin Autorización | Solución Propuesta (Requiere Aprobación) |
| :--- | :--- | :--- | :--- |
| **BLK-01: Puerto 5000 Ocupado** | PID 20404 (`Chamba/Changarro`) está escuchando en `127.0.0.1:5000`. | Terminar el proceso causaría denegación de servicio e interrupción del proyecto Changarro. | Opción A: Autorizar la detención del proceso de Changarro si ya no se requiere.<br>Opción B: Asignar un puerto alternativo a VIGÍA (ej. `VIGIA_DEV_PORT=5001`). |
| **BLK-02: Puerto 5433 Ocupado** | PID 36484 (`Chamba/Changarro/.pgdata`) está escuchando en `127.0.0.1:5433`. | `docker compose up` fallará con `port is already allocated`. Apagar postgres.exe afectaría Changarro. | Opción A: Detener la instancia PostgreSQL de Changarro.<br>Opción B: Asignar `POSTGRES_PORT=5434` en `Software/.env` de VIGÍA. |
| **BLK-03: Docker Desktop Detenido** | El servicio `com.docker.service` y el daemon de contenedores Linux están detenidos. | Ninguno destructivo, pero impide levantar `vigia-db`. | Iniciar Docker Desktop desde el menú de inicio o servicio Windows para habilitar el contenedor `vigia-db`. |

---

## 9. Dictamen Final

```
================================================================================
DICTAMEN: C. BLOQUEADO
================================================================================
```

### Justificación Técnica:
1. **Conflicto de Recursos Compartidos:** Los puertos estándar configurados para VIGÍA (`5000` para API Flask y `5433` para PostgreSQL) se encuentran ocupados por procesos activos de otro proyecto (`Chamba/Changarro`).
2. **Restricción de No Interferencia:** Las restricciones prohíben explícitamente terminar procesos desconocidos o de otros proyectos, así como modificar el archivo `.env` sin autorización previa.
3. **Dependencia de Base de Datos:** Docker Desktop se encuentra detenido y su puerto asignado colisiona con PostgreSQL local, imposibilitando la conexión con la base canónica `vigia_db`.
4. **Viabilidad de Recuperación Inmediata:** Los componentes propios de VIGÍA (PyTorch 2.6.0+cu124, acelerador RTX 4050, modelo YOLO11n, certificados TLS y Root CA de Windows) se encuentran en un estado **100% funcional y listo para operar** en cuanto se autorice resolver los dos conflictos de puertos y arrancar Docker Desktop.

---

## 10. Próximos Pasos Recomendados

Para desbloquear el entorno y proceder con la validación física real de VIGÍA, se requiere que el usuario defina:

1. **Decisión sobre los procesos de Changarro:**
   - ¿Se autoriza detener los procesos de Changarro (PID 20404 en puerto 5000 y PID 36484 en puerto 5433)?
   - O bien, ¿se autoriza reconfigurar VIGÍA en puertos libres (ej. `VIGIA_DEV_PORT=5001` y `POSTGRES_PORT=5434` en `Software/.env`)?
2. **Autorización para iniciar Docker Desktop:**
   - Proceder al arranque de Docker Desktop para levantar el contenedor `vigia-db` con su volumen persistente original `vigia_pgdata`.
