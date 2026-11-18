# INFORME TÉCNICO DE PREFLIGHT — FASE VIGIA-VISION-05B.2
## Verificación Previa y Diagnóstico de Fuentes Físicas para Validación de Clasificación de Color

**Proyecto:** VIGÍA Vision Systems  
**Fase:** VIGIA-VISION-05B.2 — Etapa A (Preflight)  
**Fecha:** 16 de noviembre de 2026  
**Auditor / Ingeniero de Visión:** Agente de Visión e Infraestructura (Google DeepMind Antigravity)  
**Ambiente:** Windows 11 Home / NVIDIA GeForce RTX 4050 Laptop GPU (6 GB VRAM) / Python 3.12 (.venv_cuda)  

---

## 1. OBJETIVO DEL PREFLIGHT

Realizar la inspección y verificación rigurosa previa a la prueba física controlada de la clasificación de color vehicular (Fase VISION-05B.2). El objetivo es constatar el estado operativo de las fuentes de video, la disponibilidad de las cámaras físicas `CAM-ENTRADA` y `CAM-SALIDA`, la resolución y tasa de fotogramas (FPS) efectiva, la integración del clasificador `VehicleColorClassifier`, la inmutabilidad de los datos, el estado deshabilitado de la persistencia relacional de color y los canales de telemetría, **sin sustituir silenciosamente fuentes físicas por videos o datos sintéticos**.

---

## 2. RESULTADOS DE LA INSPECCIÓN PREFLIGHT (PUNTOS 1 AL 9)

### 2.1. Inspección del Estado de Ambas Cámaras
- **Dispositivos Plug and Play de Windows (`Get-PnpDevice -Class Camera,Image`):**
  1. `USB2.0 HD UVC WebCam` (`USB\VID_13D3&PID_5458&MI_00\7&139903B1&0&0000`): **`Status = OK`** (Cámara física integrada activa en hardware).
  2. `Logitech BRIO` (`USB\VID_046D&PID_085E&MI_00\9&A507214&0&0000`): **`Status = Unknown`** (Desconectada físicamente del puerto USB).
- **Estado en Base de Datos PostgreSQL (`camara`):**
  - `CAM-SALIDA`: `activa = True`, `nombre = 'Cámara Carril Salida'`, `uri_stream = 'usb://0'`.
  - `CAM-ENTRADA`: `activa = True`, `nombre = 'Cámara Carril Entrada'`, `uri_stream = 'push://cam-entrada'`.
- **Estado Operativo en API REST en Vivo (`/api/v1/cameras` en PID 37220):**
  - `CAM-SALIDA`: **`TRANSMITIENDO`** (`is_transmitting = True`, `last_frame_seconds_ago = 0.26s`, secuencia acumulada: `79,044` frames).
  - `CAM-ENTRADA`: **`SIN_SEÑAL / EN ESPERA`** (`is_transmitting = False`, `last_frame_seconds_ago = 14,228.9s`, secuencia: `126` frames).

---

### 2.2. Identificación de las Fuentes Reales de Video
- **`CAM-SALIDA`:** Fuente física USB local vinculada a descriptor DirectShow `usb://0` (`USB2.0 HD UVC WebCam`, VID `13D3`, PID `5458`). Es administrada mediante un `CameraPullWorker` en segundo plano que adquiere fotogramas reales mediante OpenCV.
- **`CAM-ENTRADA`:** Canal de transporte `push://cam-entrada` configurado para recibir fotogramas mediante peticiones HTTP `POST /api/v1/cameras/CAM-ENTRADA/push` autenticadas mediante token/credencial móvil. En este instante no existe ningún cliente móvil emitiendo fotogramas hacia dicho endpoint.

---

### 2.3. Resolución y FPS Efectivos
- **`CAM-SALIDA`:**
  - Resolución nativa negociada: **`640x480`** píxeles.
  - FPS de captura e ingesta en vivo: **`0.97 FPS`** (tasa nominal del worker de supervisión en reposo con intervalo configurado de ~1.0 s por ciclo para prevención de sobrecalentamiento).
  - Tiempo de procesamiento por frame (`last_step_ms`): **`28.32 ms`** (inferencia YOLO) + **`4.49 ms`** (clasificador de color).
- **`CAM-ENTRADA`:**
  - Resolución: No negociada / inactiva.
  - FPS efectivo: **`0.0 FPS`** (sin flujo activo de datos).

---

### 2.4. Capacidad de Operación Simultánea
- La arquitectura en `VIGIA_Vision/runtime/coordinator.py` y `VIGIA_API/ingest_service.py` está validada para operar concurrentemente con múltiples cámaras (probada satisfactoriamente en VISION-05B.1 hasta 8 cámaras simultáneas a 375.6 FPS).
- Sin embargo, a nivel de **disponibilidad física en este instante**:
  - `CAM-SALIDA` está activa y lista.
  - `CAM-ENTRADA` se encuentra detenida por ausencia de emisor físico (móvil no transmitiendo o segunda cámara USB desconectada).

---

### 2.5. Pipeline de Inferencia Utilizado
- **Modelo Detector Activo:** `yolo11n.pt` (modelo base predeterminado de producción).
- **Acelerador de Hardware:** `cuda:0` (NVIDIA GeForce RTX 4050 Laptop GPU, Driver 566.36).
- **Resolución de Inferencia:** `imgsz = 640`.
- **Consumo de Memoria VRAM:** `84.32 MiB` asignados / `130.0 MiB` reservados de los 6,141 MiB disponibles.
- **Métricas de Inferencia Runtime:** 97,649 inferencias acumuladas, latencia P50 de **28.32 ms**, latencia P95 de **53.06 ms**, 0 errores CUDA, 0 conmutaciones a fallback forzado.

---

### 2.6. Integración de `VehicleColorClassifier`
- El clasificador `VehicleColorClassifier` se encuentra cableado e instanciado en el paso 7b del método `process_camera_step()` de `VisionEngineCoordinator`.
- Cuando se produce una detección vehicular positiva (`vehicle_detected = True`), se invoca de manera fail-safe `_classify_primary_vehicle_color()`, la cual aísla cualquier excepción técnica devolviendo un resultado seguro `UNKNOWN` con estado `CLASSIFIER_ERROR` sin interrumpir la operación de la cámara.

---

### 2.7. Inmutabilidad de los Datos de Entrada
- Se confirmó en código que `VehicleColorClassifier.classify()` opera sobre recortes (`crops`) en memoria derivados mediante indexación NumPy sin modificar el array BGR original del fotograma ni alterar las propiedades de `RawVehicleDetection`.

---

### 2.8. Persistencia Relacional de Color (Deshabilitada)
- Se verificó en [`VIGIA_Vision/runtime/coordinator.py`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/runtime/coordinator.py#L713-L726) que `DetectionInsertDTO` **no envía los campos de color a PostgreSQL**.
- La persistencia relacional permanece estrictamente **DESHABILITADA**, cumpliendo la regla innegociable de no modificar la base de datos de producción (`127.0.0.1:5434`) ni aplicar migraciones DDL sin autorización previa del propietario.

---

### 2.9. Mecanismos de Telemetría Disponibles
- **Supervisión de Caseta:** `GET https://127.0.0.1:5001/api/v1/supervision/status` (expone estado del motor, cámaras, latencias, frames procesados y descartes).
- **Estado de Cámara Individual:** `GET https://127.0.0.1:5001/api/v1/cameras/{codigo_camara}/status` (secuencia, detección, presencia en ROI, tiempo desde último frame).
- **Métricas Internas:** `VisionEngineCoordinator.get_operational_metrics()["color_classifier"]` (total clasificados, abstenciones `UNKNOWN`, errores técnicos y ventana deslizante de latencia).

---

## 3. RESUMEN DE HALLAZGOS Y DICTAMEN DE PREFLIGHT

| Parámetro | CAM-SALIDA | CAM-ENTRADA | Estado de Verificación |
| :--- | :---: | :---: | :---: |
| **Fuente Física** | `usb://0` (Webcam UVC) | `push://cam-entrada` (Móvil PUSH) | Identificada |
| **Hardware Físico** | Conectado (`Status: OK`) | Desconectado (`BRIO Unknown`) / Móvil inactivo | **PARCIAL** |
| **Estado en Servicio** | `TRANSMITIENDO` (0.26s ago) | `SIN_SEÑAL / EN ESPERA` (14,228s ago) | **BLOQUEO PREVENTIVO** |
| **Resolución** | `640x480` | No disponible | Identificada |
| **FPS Efectivos** | `0.97 FPS` continuo | `0.0 FPS` | Reportado |
| **Clasificador Color** | Integrado en coordinator | Integrado en coordinator | **CONFORME** |
| **Inmutabilidad** | Verificada | Verificada | **CONFORME** |
| **Persistencia Color** | Deshabilitada en BD | Deshabilitada en BD | **CONFORME** |
| **Telemetría** | Operativa | Operativa | **CONFORME** |

---

## 4. DETENCIÓN CONTROLADA Y SOLICITUD DE AUTORIZACIÓN AL OPERADOR

Conforme a la **Instrucción 12** y a la **Regla Innegociable de Preflight**:

> *"Si alguna cámara no está disponible, detener la ejecución de esa parte y reportar el problema. No sustituir silenciosamente una fuente física por un video de prueba. No iniciar la prueba física hasta confirmar que las dos cámaras están disponibles y que el operador ha autorizado su ejecución."*

Se **detiene preventivamente el avance hacia la Fase B (Validación Multicámara)** y se notifica formalmente al operador del sistema:

1. **`CAM-SALIDA`** está lista, transmitiendo en vivo y disponible para la validación física observacional del clasificador de color sobre fotogramas reales capturados por la webcam.
2. **`CAM-ENTRADA`** se encuentra actualmente detenida por falta de flujo de datos físico (el cliente móvil no está transmitiendo al endpoint PUSH y la cámara USB externa `Logitech BRIO` está desconectada del equipo).

### Opciones de Continuación para el Operador:
- **Opción 1:** Conectar físicamente la cámara USB secundaria (`Logitech BRIO`) al equipo para asignarla al carril de entrada.
- **Opción 2:** Iniciar la transmisión desde el dispositivo móvil emparejado a través de la interfaz web `https://<IP>:5001/mobile` hacia `CAM-ENTRADA`.
- **Opción 3:** Autorizar la ejecución de la validación física observacional de forma inmediata sobre la cámara actualmente activa (`CAM-SALIDA`), o proporcionar un lote de validación física controlada para el carril de entrada.

---
*Fin del Informe Técnico de Preflight VIGIA-VISION-05B.2.*
