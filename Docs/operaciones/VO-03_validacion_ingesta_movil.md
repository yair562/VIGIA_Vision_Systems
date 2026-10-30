# VO-03 — Validación Operativa de Ingesta Móvil hacia VIGÍA Vision

## Control Documental
- **Identificador:** `VO-03` / `VO-04E`
- **Título:** Servicio de Ingesta HTTP/TLS, Autenticación Fail-Closed, Selección Dinámica de IP Wi-Fi, Resolución por Generación Activa e Interfaz Web Móvil
- **Fecha de Elaboración:** 29 de octubre de 2026
- **Estado Técnico de Implementación:** `IMPLEMENTADO, AUDITADO, CORREGIDO Y VALIDADO (VO-04E)`
- **Estado de Pruebas Automatizadas:** `PRUEBAS AUTOMATIZADAS APROBADAS` (49/49 unitarias de ingesta, 162/162 suite completa del sistema)
- **Estado de la Validación Física:** `VALIDACIÓN FÍSICA: BLOQUEADA — pendiente de ejecución con un teléfono real`
- **Commit Base:** [`85d2eb0`](../../) (`feat(vision): integrate YOLO vehicle detector`)

---

## 1. Objetivo y Alcance Autorizado

### 1.1. Objetivo
Implementar y securizar el camino técnico mínimo para conectar un teléfono celular físico con el motor propio de visión artificial de VIGÍA:

$$\text{Cámara de Teléfono Móvil} \xrightarrow[\text{Contexto Seguro}]{\text{HTTPS / TLS}} \text{Interfaz Web} \xrightarrow[\text{X-Camera-Key}]{\text{POST Ingest}} \text{VIGIA\_API} \xrightarrow[\text{Atomic Lock}]{\text{push\_frame + step}} \text{Coordinator} \longrightarrow \text{YOLO11n} \longrightarrow \text{VisionResult}$$

### 1.2. Alcance Autorizado y Resolución de Auditoría (VO-03B)
1. **Selección Tecnológica de Servidor y TLS:**
   - **Prueba física / Validación local:** Servidor Werkzeug con soporte nativo TLS mediante certificado autofirmado generado específicamente para VIGÍA (`generate_vigia_tls_certificate`). Permite cumplir el requisito estricto de los navegadores móviles (`window.isSecureContext === true`) sin instalar paquetes de terceros ni dependencias externas.
   - **Despliegue operativo definitivo / Producción:** Servidor WSGI `Waitress` ejecutándose en localhost detrás de un terminador TLS inverso (Nginx / Caddy / reverse proxy de infraestructura). Waitress no implementa TLS directamente de fábrica, por lo que no debe exponerse directamente sin terminador seguro.
2. **Autenticación Obligatoria Fail-Closed:**
   - Si no se suministra un token de autenticación (`auth_token` nulo o vacío), el servicio opera en modo seguro *fail-closed* y rechaza peticiones de ingesta con HTTP 503 (`Service Unavailable`), impidiendo que el motor quede desprotegido en la red.
   - La validación del token de cámara (`X-Camera-Key` o `Bearer`) se realiza en tiempo constante mediante `hmac.compare_digest` para evitar ataques de temporización.
3. **Atomicidad y Resolución de Condición de Carrera:**
   - Debido a que `MobilePushFrameBuffer` implementa una ranura única de memoria (capacidad 1), el depósito del fotograma (`push_frame`) y la ejecución del ciclo de inferencia del coordinador (`process_camera_step`) se ejecutan de manera indivisible bajo el mismo cerrojo de concurrencia (`process_lock`). Esto evita que una petición concurrente sobrescriba el fotograma antes de que sea procesado por YOLO.
4. **Protección de Credenciales y Secretos:**
   - Ninguna clave secreta o cadena de conexión de base de datos se almacena en texto claro en comandos de arranque o código fuente. Todo se administra vía variables de entorno (`VIGIA_DB_DSN`, `VIGIA_CAMERA_KEY`).

### 1.3. Restricciones Respetadas
- **Base de Datos y PostgreSQL:** Intacta (sin modificaciones en `BD/`, tablas, DDL, migraciones ni datos).
- **Contratos Protegidos:** Intactos ([`VisionResult`](../../VIGIA_Core/domain/vision_result.py), [`AccessDecision`](../../VIGIA_Core/domain/access_decision.py), [`IDetectionRepository`](../../VIGIA_Core/repository/detection_repository.py)).
- **Prototipo Experimental:** [`VR_Semaforo/`](../../VR_Semaforo) no fue modificado, ni se copiaron sus certificados (`cert.pem`, `key.pem`) ni scripts (`generate_cert.py`).
- **Detector YOLO:** Conserva `YOLO11n` en CPU bajo [`YoloVehicleDetector`](../../VIGIA_Vision/detection/yolo_detector.py).
- **Control de Versiones:** Sin `git push`, sin creación de commits no autorizados.

---

## 2. Arquitectura del Flujo Implementado

```text
[ Teléfono Móvil ]
      │ (getUserMedia - Cámara Trasera en Contexto Seguro HTTPS)
      ▼
[ VIGIA_Dashboard/mobile/index.html ] (Captura bajo demanda -> JPEG Blob)
      │
      │ HTTPS POST /api/v1/cameras/<codigo_camara>/push
      │ Headers: Content-Type: multipart/form-data, X-Camera-Key: <token>
      ▼
[ VIGIA_API/ingest_service.py ]
      ├── 1. Valida modo Fail-Closed: auth_token configurado (HTTP 503 si ausente)
      ├── 2. Valida Autorización en tiempo constante: hmac.compare_digest (HTTP 401 si no coincide)
      ├── 3. Valida Tamaño (<= 8 MiB) y presencia de bytes en campo 'frame' (HTTP 400 / 413)
      ├── 4. Decodifica mediante OpenCV: cv2.imdecode(bytes) -> BGR ndarray (HTTP 422 si corrupto)
      ├── 5. Valida dimensiones máximas (<= 3840 x 2160) (HTTP 422 si excede)
      ├── 6. Valida contrato de dominio: validate_bgr_frame(frame)
      ├── 7. Resuelve slot en CameraSourceRegistry -> BoundCameraSlot (HTTP 404 / 400)
      │
      └── SECCIÓN CRÍTICA ATÓMICA (with process_lock):
            ├── 8. Deposita en ranura única: MobilePushFrameBuffer.push_frame(frame)
            └── 9. Ejecuta inferencia: coordinator.process_camera_step(codigo_camara)
                        ├── read_frame() -> Frame vigente (TTL <= 3.0s, is_already_processed=False)
                        ├── Proyección geométrica de ROI (PixelROI)
                        ├── Inferencia con YoloVehicleDetector (YOLO11n CPU)
                        ├── Filtrado por ROI y clases COCO vehiculares
                        └── Construcción de VisionObservationEnvelope (VisionResult)
                  │
                  ▼
[ Respuesta JSON HTTP 200 ] ───> Interfaz móvil muestra estado, tipo de vehículo y confianza
```

---

## 3. Especificación de la API de Ingesta (`VIGIA_API`)

### 3.1. `GET /mobile`
- **Propósito:** Sirve la interfaz web móvil de captura para navegadores de celular.
- **Respuesta:** Archivo `text/html` responsivo con vista previa en vivo, campo obligatorio de clave de acceso y controles táctiles.

### 3.2. `POST /api/v1/cameras/<codigo_camara>/push`
- **Propósito:** Ingesta de un fotograma físico individual hacia el buffer de la cámara indicada.
- **Parámetros de Ruta:** `codigo_camara` (ej. `'CAM-ENTRADA'` o `'CAM-SALIDA'`). Debe pertenecer a la topología operativa validada.
- **Encabezados:**
  - `Content-Type: multipart/form-data` con campo `frame` (o `image`).
  - `X-Camera-Key: <token>` o `Authorization: Bearer <token>` (**obligatorio**).
- **Límites de Seguridad:**
  - Carga útil máxima: **8 MiB** (HTTP 413 si se excede).
  - Dimensiones máximas: **3840 × 2160 píxeles** (HTTP 422 si se excede).
  - Rechazo de archivos vacíos o corruptos: HTTP 400 / 422.
- **Respuestas:**
  - `200 OK`: Fotograma procesado correctamente. Retorna:
    ```json
    {
      "ok": true,
      "codigo_camara": "CAM-ENTRADA",
      "frame_sequence": 1,
      "status": "VEHICLE_DETECTED_NO_PLATE",
      "vehicle_detected": true,
      "tipo_vehiculo": "AUTOMOVIL",
      "confianza": 0.91,
      "in_roi_now": 1,
      "total_detected_in_frame": 1,
      "timestamp": "2026-10-29T14:40:00Z"
    }
    ```
  - `401 Unauthorized`: Token de cámara ausente o incorrecto.
  - `503 Service Unavailable`: Modo fail-closed activado (servicio sin clave configurada) o coordinador no disponible.
  - `404 Not Found`: Código de cámara no registrado en la topología activa.
  - `400 Bad Request`: Cámara no admite modo push o carga útil vacía.
  - `413 Payload Too Large`: Archivo mayor a 8 MiB.
  - `422 Unprocessable Entity`: Bytes corruptos o dimensiones excedidas.
  - `500 Internal Server Error`: Fallo interno sin filtración de trazas ni rutas del sistema.

---

## 4. Requisitos de Seguridad y Contexto de Red Móvil (HTTPS)

### 4.1. Justificación de Servidor TLS para Pruebas Operativas
Waitress es un servidor WSGI puro de alto rendimiento para entornos controlados, diseñado para delegar la terminación SSL/TLS a un servidor proxy inverso (Nginx, Caddy o Envoy). Para la validación física en campo en la red Wi-Fi de la caseta:
1. Instalar y configurar un proxy inverso en la máquina del operador agregaría software externo no autorizado al alcance del sprint.
2. `Werkzeug` cuenta con integración directa con sockets TLS utilizando la biblioteca estándar `ssl` de Python.
3. Por tanto, `run_ingest_server()` utiliza el servidor integrado de `Werkzeug` provisto de un contexto SSL nativo para la prueba física local, garantizando transporte cifrado y contexto seguro sin dependencias externas.

### 4.2. Certificados TLS Auto-firmados de VIGÍA
Para garantizar que el navegador móvil admita la cámara (`navigator.mediaDevices.getUserMedia`), se implementó la función generadora:
[`generate_vigia_tls_certificate(target_ip, cert_path, key_path, valid_days)`](../../VIGIA_API/ingest_service.py)
- **Algoritmo:** Clave privada RSA de 2048 bits con exponente público 65537.
- **Firma:** X.509 v3 auto-firmado mediante SHA-256.
- **Subject Alternative Names (SAN):** Incluye la IP de red local del equipo (ej. `192.168.1.85`), `127.0.0.1` y `localhost`.
- **Validez:** Temporal para pruebas de campo (30 días por omisión).

### 4.3. Restricción de Interfaces de Red
Para mitigar la exposición accidental del servicio en redes públicas, se recomienda enlazar `host` a la dirección IP local específica asignada a la interfaz de la caseta (ej. `192.168.1.85`), en lugar de utilizar `0.0.0.0` sin filtrado.

### 4.4. Resolución por Generación Activa, SSoT y Recuperación Segura (VO-04E)
Para erradicar la división de fuente de verdad (*split-brain*) y garantizar que el servidor siempre consuma una pareja íntegra y validada:
1. **Manifiesto como Única Fuente de Verdad (*SSoT*):** Cuando existe `active_generation.json`, este identifica taxativamente la generación activa autorizada. No se consultan primero los archivos canónicos.
2. **Validación Estricta de Rutas y Anti-Traversal:** Se valida la estructura del manifiesto (`generation_id`, `cert_relpath`, `key_relpath`) y se verifica que las rutas apunten sin excepción dentro de `generations/<gen_id>/`, rechazando rutas absolutas, secuencias de escape `..` o escapes por symlinks.
3. **Entrega de Rutas Versionadas a Werkzeug:** [`run_ingest_server()`](../../VIGIA_API/ingest_service.py) recibe y entrega a Werkzeug las rutas físicas de los archivos versionados validados (`generations/<gen_id>/vigia_cert.pem` y `generations/<gen_id>/vigia_key.pem`), desacoplando el runtime HTTPS de los archivos canónicos.
4. **Sincronización Secundaria Segura de Canónicos:** Los archivos canónicos (`vigia_cert.pem`, `vigia_key.pem`) se mantienen exclusivamente por compatibilidad con herramientas externas y se sincronizan desde la generación versionada activa de forma secundaria (*best-effort*). Si los canónicos faltan, difieren en bytes o tienen claves cruzadas, esa discrepancia no invalida la generación activa ni altera las rutas entregadas a Werkzeug.
5. **Modo de Compatibilidad Heredada:** Si el manifiesto no existe en disco, se evalúa el par canónico completo existente. Si ambos archivos existen y forman un par válido con vigencia y SAN correcto, se utilizan; en caso contrario, se rechaza el arranque con `FileNotFoundError`.
6. **Limitaciones Permanentes:** Ningún sistema de archivos comercial permite actualizar dos archivos independientes (`vigia_cert.pem` y `vigia_key.pem`) en una única operación indivisible del kernel; por diseño arquitectónico, el manifiesto es el único punto atómico de conmutación.

---

## 5. Resultados de Pruebas Automatizadas

Se cuenta con 49 pruebas unitarias en [`tests/unit/test_mobile_ingest_api.py`](../../tests/unit/test_mobile_ingest_api.py), ejecutadas en memoria mediante el cliente de pruebas WSGI:

| ID de Prueba | Componente / Validación | Resultado |
| :--- | :--- | :---: |
| `PU-INGEST-01` | `GET /mobile` entrega interfaz HTML (`text/html`) con controles de cámara | **Aprobado** |
| `PU-INGEST-02` | Rechazo de solicitud sin archivo / cuerpo vacío (HTTP 400) | **Aprobado** |
| `PU-INGEST-03` | Rechazo de archivo de imagen con 0 bytes (HTTP 400) | **Aprobado** |
| `PU-INGEST-04` | Rechazo de bytes corruptos no decodificables con OpenCV (HTTP 422) | **Aprobado** |
| `PU-INGEST-05` | Rechazo de fotograma con dimensiones superiores al límite (HTTP 422) | **Aprobado** |
| `PU-INGEST-06` | Rechazo de carga superior a 8 MiB (HTTP 413) | **Aprobado** |
| `PU-INGEST-07` | Rechazo de cámara no registrada en la topología (HTTP 404) | **Aprobado** |
| `PU-INGEST-08` | Rechazo de cámara configurada como RTSP/pull para ingesta push (HTTP 400) | **Aprobado** |
| `PU-INGEST-09` | Control de autorización: rechazo con token inválido/ausente (HTTP 401) | **Aprobado** |
| `PU-INGEST-10` | Control de autorización: aceptación con token correcto (HTTP 200) | **Aprobado** |
| `PU-INGEST-11` | Recepción válida, entrega a `MobilePushFrameBuffer` e inferencia (HTTP 200) | **Aprobado** |
| `PU-INGEST-12` | Fallo de inferencia encapsulado limpiamente como `VISION_ERROR` (HTTP 200) | **Aprobado** |
| `PU-INGEST-13` | Rechazo de métodos HTTP no permitidos (HTTP 405) | **Aprobado** |
| `PU-INGEST-14` | Excepción crítica inesperada manejada con HTTP 500 sin exponer rutas | **Aprobado** |
| `PU-INGEST-15` | Manejo de indisponibilidad cuando el coordinador es nulo (HTTP 503) | **Aprobado** |
| `PU-INGEST-16` | **Modo seguro fail-closed:** deniega push con HTTP 503 si no hay clave configurada | **Aprobado** |
| `PU-INGEST-17` | **Generación TLS de VIGÍA:** crea par cert/key con SAN para IP local y localhost | **Aprobado** |
| `PU-INGEST-18` | **Atomicidad de concurrencia:** serialización estricta de push_frame e inferencia | **Aprobado** |
| `PU-INGEST-19` | **Validación par TLS:** aceptación de par certificado y clave válidos y coincidentes | **Aprobado** |
| `PU-INGEST-20` | **Rechazo par TLS inválido:** detección y fallo ante clave y certificado no coincidentes | **Aprobado** |
| `PU-INGEST-21` | **Rechazo certificado vencido:** detección y fallo ante certificados expirados | **Aprobado** |
| `PU-INGEST-22` | **Rechazo SAN ausente:** detección y fallo si el certificado no incluye la IP de acceso | **Aprobado** |
| `PU-INGEST-23` | **Protección de sobrescritura:** prevención de regeneración silenciosa (`overwrite=False`) | **Aprobado** |
| `PU-INGEST-24` | **Rechazo IP ajena:** detección y fallo si la IP no pertenece a interfaces locales activas | **Aprobado** |
| `PU-INGEST-25` | **Aceptación IP local:** resolución y validación de direcciones locales del PC | **Aprobado** |
| `PU-INGEST-26` | **Limpieza documental:** verificación de ausencia de credenciales operativas literales | **Aprobado** |
| `PU-INGEST-27` | **Detección dinámica Wi-Fi:** identificación de interfaz física Wi-Fi activa y su IPv4 | **Aprobado** |
| `PU-INGEST-28` | **Rechazo Wi-Fi inactiva:** detección de Wi-Fi desconectada sin enlace activo | **Aprobado** |
| `PU-INGEST-29` | **Rechazo APIPA / Loopback:** exclusión estricta de 169.254.x.x y 127.0.0.1 | **Aprobado** |
| `PU-INGEST-30` | **Ambigüedad de interfaces:** detención ante múltiples Wi-Fi sin selección preferida | **Aprobado** |
| `PU-INGEST-31` | **Selección preferida:** resolución exitosa de interfaz Wi-Fi específica (`preferred_interface`) | **Aprobado** |
| `PU-INGEST-32` | **Sin sustitución por Ethernet:** rechazo estricto de fallback a Ethernet si Wi-Fi falta | **Aprobado** |
| `PU-INGEST-33` | **Incoherencia SAN por cambio de IP:** detención preventiva ante cambio de IP Wi-Fi | **Aprobado** |
| `PU-INGEST-34` | **Regeneración autorizada:** regeneración explícita de certificado ante nueva IP | **Aprobado** |
| `PU-INGEST-35` | **Generación y validación atómica:** verificación de staging, manifiesto y par canónico | **Aprobado** |
| `PU-INGEST-36` | **Resiliencia ante fallo RSA:** preservación intacta del par anterior ante fallo de clave | **Aprobado** |
| `PU-INGEST-37` | **Resiliencia ante fallo de firma:** preservación intacta del par anterior ante error x509 | **Aprobado** |
| `PU-INGEST-38` | **Cancelación preventiva:** fallo en pre-validación staging cancela y protege par activo | **Aprobado** |
| `PU-INGEST-39` | **Recuperación segura:** restauración desde generación activa sin mezclar pares | **Aprobado** |
| `PU-INGEST-40` | **Reemplazo atómico de manifiesto:** transición sin estados intermedios ni huérfanos | **Aprobado** |
| `PU-INGEST-41` | **Arranque normal:** consumo del par versionado activo sin regeneraciones redundantes | **Aprobado** |
| `PU-INGEST-42` | **Resolución G2 con canónicos G1:** prevalencia del manifiesto G2 y sincronización | **Aprobado** |
| `PU-INGEST-43` | **Resolución G2 con canónicos cruzados:** reparación de par canónico inconsistente | **Aprobado** |
| `PU-INGEST-44` | **Rechazo de manifiesto corrupto:** fallo seguro (fail-closed) sin fallback ciego | **Aprobado** |
| `PU-INGEST-45` | **Anti-traversal en manifiesto:** rechazo de rutas con `..`, absolutas o fuera de carpeta | **Aprobado** |
| `PU-INGEST-46` | **Archivos versionados ausentes:** fallo seguro si la generación referenciada falta | **Aprobado** |
| `PU-INGEST-47` | **Incoherencia SAN en generación activa:** rechazo si la IP de acceso difiere | **Aprobado** |
| `PU-INGEST-48` | **Compatibilidad heredada:** resolución de par canónico válido sin manifiesto | **Aprobado** |
| `PU-INGEST-49` | **Entrega de rutas a Werkzeug:** confirmación de paso de rutas versionadas activas | **Aprobado** |

**Regresión de la suite completa:** **162 pruebas ejecutadas, 162 aprobadas (0 errores, 0 fallos)** en 22.48 segundos.

---

## 6. Procedimiento para la Prueba Física con Teléfono Real

> [!IMPORTANT]
> **Estado de la Prueba Física:**
> `VALIDACIÓN FÍSICA: BLOQUEADA — pendiente de ejecución con un teléfono real.`
> En cumplimiento estricto del protocolo, no se utilizaron imágenes pregrabadas para simular la cámara física del celular. La prueba física real requiere la interacción presencial del operador siguiendo estos pasos:

### 6.1. Selección Dinámica de la Interfaz Wi-Fi
El sistema incorpora detección automática de la interfaz Wi-Fi física activa del PC mediante [`discover_wifi_ipv4()`](../../VIGIA_API/ingest_service.py).
- **Sin escritura manual de IP:** El operador no necesita conocer ni escribir la IP antes de arrancar.
- **Exclusión estricta:** Se descartan automáticamente direcciones de loopback, APIPA (`169.254.0.0/16`), adaptadores virtuales (WSL, VMware, VirtualBox) y conexiones por cable Ethernet.
- **Múltiples interfaces Wi-Fi:** Si el equipo dispone de más de una interfaz inalámbrica activa, el arranque se detiene de forma segura para evitar enlaces ambiguos. En tal caso, el operador define `$env:VIGIA_WIFI_INTERFACE = "Nombre-Interfaz"`.
- **Cambio de IP Wi-Fi (DHCP):** Si el router asigna una IP diferente a la grabada previamente en el SAN del certificado, el servidor detiene el arranque (`TLSConfigError`) para evitar discrepancias. Para regenerar el certificado para la nueva IP con confirmación explícita, se ejecuta el arranque con `$env:VIGIA_REGENERATE_CERT = "1"`.

### 6.2. Consideraciones Especiales en Redes Escolares o Corporativas
- **Aislamiento de Clientes (*AP Client Isolation*):** En redes Wi-Fi institucionales o de invitados, los puntos de acceso suelen bloquear el tráfico directo entre dispositivos (aislamiento de capa 2/3). Si esto ocurre, el teléfono no podrá alcanzar la IP del PC (`ERR_CONNECTION_TIMED_OUT`). Se recomienda utilizar un punto de acceso o router dedicado para la caseta de control sin aislamiento de clientes.
- **Bloqueo de Puertos No Estándar:** Algunas redes restringen puertos distintos a 80 y 443. Si el puerto `8443` está bloqueado por políticas de red institucional, se requiere autorización para utilizar una red privada controlada.
- **Portales Cautivos:** Tanto el PC como el teléfono deben haber completado cualquier autenticación previa de portal cautivo antes de iniciar la ingesta.

### 6.3. Paso a Paso para el Operador

1. **Configurar las variables de entorno obligatorias en PowerShell:**
   > [!IMPORTANT]
   > No incrustar contraseñas operativas literales ni tokens en scripts de consola. Configurar las variables con los valores reales del entorno local antes de arrancar.
   ```powershell
   $env:VIGIA_DB_DSN = "postgresql://<db_user>:<db_password>@127.0.0.1:5433/<db_name>"
   $env:VIGIA_CAMERA_KEY = "<clave_de_acceso_autorizada>"
   # Opcional: solo si hay múltiples tarjetas Wi-Fi activas
   # $env:VIGIA_WIFI_INTERFACE = "Wi-Fi"
   # Opcional: solo si la IP cambió y se requiere regenerar el certificado explícitamente
   # $env:VIGIA_REGENERATE_CERT = "1"
   ```

2. **Iniciar el servidor de ingesta HTTPS con selección automática de Wi-Fi:**
   ```powershell
   cd C:\GEST.PROY.TI\Software\VIGIA_Vision_Systems
   .\.venv\Scripts\python.exe -c "
   import os
   from pathlib import Path
   from VIGIA_API.ingest_service import (
       create_ingest_app,
       discover_wifi_ipv4,
       generate_vigia_tls_certificate,
       regenerate_vigia_tls_certificate,
       run_ingest_server,
       validate_tls_certificate_pair,
   )
   from VIGIA_Vision.runtime.coordinator import VisionEngineCoordinator
   from VIGIA_Vision.detection.yolo_detector import YoloVehicleDetector, YoloDetectorConfig
   from VIGIA_Vision.config.topology_validator import TopologyValidator, PsycopgTopologyConfigRepository

   # 1. Validación de variables de entorno obligatorias
   camera_key = os.environ.get('VIGIA_CAMERA_KEY')
   db_dsn = os.environ.get('VIGIA_DB_DSN')

   if not camera_key:
       raise SystemExit('Error operativo: Variable VIGIA_CAMERA_KEY no configurada.')
   if not db_dsn:
       raise SystemExit('Error operativo: Variable VIGIA_DB_DSN no configurada.')

   # 2. Detección automática y dinámica de la IP Wi-Fi activa
   pref_if = os.environ.get('VIGIA_WIFI_INTERFACE')
   if_name, wifi_ip = discover_wifi_ipv4(preferred_interface=pref_if)
   print(f'=== Interfaz Wi-Fi detectada: {if_name} | IPv4: {wifi_ip} ===')

   # 3. Certificados TLS propios de VIGIA para la IP detectada (manejo atómico y manifiesto)
   cert_dir = Path('certs')
   cert_dir.mkdir(exist_ok=True)
   cert_path = cert_dir / 'vigia_cert.pem'
   key_path = cert_dir / 'vigia_key.pem'
   regen_flag = os.environ.get('VIGIA_REGENERATE_CERT') == '1'

   if not cert_path.exists() or not key_path.exists():
       generate_vigia_tls_certificate(target_ip=wifi_ip, cert_path=cert_path, key_path=key_path)
   elif regen_flag:
       regenerate_vigia_tls_certificate(target_ip=wifi_ip, cert_path=cert_path, key_path=key_path)
       print('AVISO: Certificado regenerado. Limpie la variable en PowerShell: $env:VIGIA_REGENERATE_CERT = $null')
   else:
       # Resolver y validar atómicamente par canónico y manifiesto
       from VIGIA_API.ingest_service import resolve_active_tls_pair
       resolve_active_tls_pair(cert_dir_or_cert_path=cert_path, key_path=key_path, target_ip=wifi_ip)

   # 4. Inicializar motor de detección y topología
   detector = YoloVehicleDetector(YoloDetectorConfig(model_path='yolo11n.pt'))
   repo = PsycopgTopologyConfigRepository(dsn=db_dsn)
   validator = TopologyValidator(repository=repo)
   coordinator = VisionEngineCoordinator(topology_validator=validator, detector=detector)
   coordinator.initialize()

   # 5. Crear app e iniciar servidor Werkzeug TLS
   app = create_ingest_app(coordinator=coordinator, auth_token=camera_key)
   access_url = f'https://{wifi_ip}:8443/mobile'
   print(f'=== Servidor de Ingesta VIGIA iniciado en {access_url} ===')
   run_ingest_server(app, host=wifi_ip, port=8443, ssl_cert=cert_path, ssl_key=key_path)
   "
   ```

3. **Conectar el teléfono a la misma red Wi-Fi y abrir:**
   `https://<IP_WIFI_DETECTADA>:8443/mobile`
   - El navegador mostrará una advertencia de certificado auto-firmado (`NET::ERR_CERT_AUTHORITY_INVALID`). Pulsar **"Configuración avanzada"** -> **"Continuar a <IP_WIFI_DETECTADA> (no seguro)"**.

4. **Ejecutar la captura física:**
   - En el campo **"Clave de Acceso"**, ingresar el valor secreto configurado en `$env:VIGIA_CAMERA_KEY`.
   - Presionar **"Activar Cámara"** y aceptar el permiso de cámara del navegador.
   - Apuntar hacia un vehículo (o modelo de prueba).
   - Presionar **"Capturar y Enviar a VIGÍA"**.
   - Verificar que el panel de resultados muestre `AUTOMOVIL` y la confianza calculada por `YOLO11n` en tiempo real.
