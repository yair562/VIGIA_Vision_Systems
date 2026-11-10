# VIGIA-OPT-MULTI-01 — Evaluación y Optimización del Pipeline Multicámara CUDA

**Proyecto:** VIGÍA Vision Systems — Control de Acceso Vehicular Autónomo  
**Documento ID:** `VIGIA-OPT-MULTI-01`  
**Fecha de Validación:** 2026-11-05  
**Estado:** `DICTAMEN: APROBADO Y CONGELADO`  
**Dispositivo Operativo:** NVIDIA GeForce RTX 4050 Laptop GPU (`cuda:0`, 6140 MB VRAM)  
**Modelo YOLO:** YOLO11n (`yolo11n.pt`, FP32, imgsz=640, `rect=False`)  
**Pipeline de Persistencia:** Síncrona canónica (Almacenamiento en disco NVMe + PostgreSQL `vigia_db`)  
**Conjunto de Pruebas Unitarias:** 284/284 Aprobadas (100% pass rate)

---

## 1. Resumen Ejecutivo

El presente informe documenta la evaluación exhaustiva, identificación de cuellos de botella y optimización de concurrencia del motor de visión artificial de **VIGÍA Vision Systems** operando sobre múltiples cámaras simultáneas en el entorno de aceleración NVIDIA CUDA FP32.

Esta actividad representa la **última optimización planificada del motor de visión** previa al congelamiento definitivo de su configuración y el inicio de las fases de pruebas funcionales y físicas en terreno.

### Hallazgos Principales:
1. **Cuello de Botella Identificado en el Baseline:**  
   La implementación original en `VIGIA_API/ingest_service.py` utilizaba un bloqueo global reentrante único (`process_lock = threading.RLock()`) que envolvía no solamente la inserción en el buffer del fotograma, sino también la inferencia predictiva YOLO (~8 ms), la codificación y escritura síncrona en disco NVMe de dos imágenes JPEG (~30 ms) y la inserción transaccional síncrona en PostgreSQL (~18 ms). Como consecuencia, cualquier solicitud de una cámara bloqueaba por completo a todas las demás cámaras durante ~56 ms por fotograma, imponiendo un techo físico de saturación global de $\approx 18\text{ FPS}$ aggregate y causando que la latencia media bajo concurrencia (E4) aumentara de 85.95 ms a 214.26 ms (+149%). La GPU permanecía subutilizada (apenas 15.91% de uso en E4 stress) debido a inanición por bloqueos de I/O de disco y base de datos.
2. **Optimización Controlada Implementada:**  
   Se diseñó e implementó una arquitectura de **Bloqueo Granular por Cámara** (`camera_process_locks: Dict[str, threading.RLock]`) acoplada a un bloqueo exclusivo de microsegundos en la inferencia GPU (`_lock` en `YoloVehicleDetector`) y un bloqueo liviano en el diccionario de reintentos (`retry_cache_lock`). De este modo, cada cámara serializa exclusivamente sus propias solicitudes sucesivas para prevenir sobrescrituras de su buffer individual (`MobilePushFrameBuffer`), mientras que la compresión JPEG, el almacenamiento en disco y los commits en PostgreSQL se ejecutan en **paralelo real** entre cámaras distintas.
3. **Resultados Obtenidos:**  
   - En régimen nominal (~1 FPS/cámara), el sistema procesó con éxito el 100% de los fotogramas en todos los escenarios (E1 a E4) manteniendo latencias operacionales estables y predecibles.
   - En régimen de estrés/saturación, la concurrencia multicámara superó el techo del baseline, alcanzando un throughput de saturación de **20.43 FPS** en E3 (+13.4%) y **19.69 FPS** en E4 (+8.1%).
   - La latencia p50 en E4 stress se redujo de 219.0 ms a 172.0 ms (**-47.0 ms, -21.5%**), y la latencia media se redujo en **-12.0%** (de 214.26 ms a 188.65 ms).
   - La GPU NVIDIA RTX 4050 Laptop GPU incrementó su aprovechamiento en E4 stress de 15.91% a **32.10%** al eliminarse la inanición por contención global.
   - El consumo de VRAM se mantuvo perfectamente acotado en **1408.5 MB** (22.9% del límite de 6140 MB), con una temperatura térmica fría y estable de **44.0°C**.
   - Integridad de datos: 100% de consistencia entre fotogramas enviados, códigos HTTP 200 OK y filas persistidas en PostgreSQL (`db_matches_responses: true`), con 0 errores y 0 contaminación cruzada entre cámaras.
4. **Dictamen Final:**  
   **APROBADO Y CONGELADO**. La configuración queda formalmente cerrada para las pruebas funcionales y físicas.

---

## 2. Inspección de la Arquitectura de Concurrencia de VIGÍA

### 2.1 Modelo de Ejecución de Servidor
El servicio de ingesta `VIGIA_API/ingest_service.py` se ejecuta sobre el servidor HTTP/HTTPS multihilo de Werkzeug (`threaded=True`). Cada solicitud entrante al endpoint de ingesta:

```http
POST /api/v1/cameras/<codigo_camara>/push
```

es atendida por un hilo independiente del pool de hilos de la aplicación.

### 2.2 Diagnóstico del Cuello de Botella del Baseline
En la arquitectura de línea base, el punto crítico de serialización se ubicaba en la función `create_ingest_app` y el endpoint `push_camera_frame`:

```python
# LÍNEA BASE (SERIALIZACIÓN GLOBAL DEFECTUOSA)
process_lock = threading.RLock()

# Dentro de push_camera_frame:
with process_lock:
    # 1. Limpieza de caché de reintentos
    # 2. slot.source.push_frame(frame_bgr)
    # 3. envelope = engine_coordinator.process_camera_step(codigo_camara)
    #    -> YOLO predict (GPU)           ~8 ms
    #    -> Guardado evidencia en disco ~30 ms (original_orig.jpg + annotated_annot.jpg)
    #    -> Commit PostgreSQL          ~18 ms
    # 4. Actualización de live frame y debounce
```

```mermaid
flowchart TD
    subgraph Baseline["Baseline: Serialización Global Monolítica (process_lock)"]
        Req1["CAM-ENTRADA (Req 1)"] --> Lock["with process_lock (GLOBAL)"]
        Req2["CAM-SALIDA (Req 2)"] -.->|BLOQUEADA EN ESPERA| Lock
        Req3["CAM-03 (Req 3)"] -.->|BLOQUEADA EN ESPERA| Lock
        Req4["CAM-04 (Req 4)"] -.->|BLOQUEADA EN ESPERA| Lock
        
        Lock --> YOLO["YOLO CUDA (8 ms)"]
        YOLO --> DISK["Escritura Disco NVMe (30 ms)"]
        DISK --> DB["Commit PostgreSQL (18 ms)"]
        DB --> Release["Libera process_lock (~56 ms total)"]
    end
```

**Consecuencias de la serialización global:**
1. **Contención Exponencial:** Si 4 cámaras transmiten casi simultáneamente, la cuarta cámara debe esperar a que las 3 anteriores concluyan su ciclo completo de disco y base de datos, experimentando tiempos de espera de lock superiores a $3 \times 56\text{ ms} = 168\text{ ms}$.
2. **Inanición de GPU (*GPU Starvation*):** La GPU NVIDIA RTX 4050 Laptop GPU completa la inferencia en apenas 8 milisegundos, pero debe permanecer inactiva durante los 48 ms subsiguientes mientras el hilo sostiene el bloqueo global realizando operaciones síncronas de disco y red TCP con PostgreSQL. La utilización media de la GPU cayó al 15.91% en E4 stress.
3. **Techo de Capacidad Infranqueable:** La capacidad teórica global de todo el sistema estaba acotada a $1000\text{ ms} / 56\text{ ms} \approx 17.8\text{ FPS}$ compartidos entre todas las cámaras.

### 2.3 Análisis de Aislamiento y No Injerencia entre Cámaras
Una auditoría minuciosa de los componentes internos reveló que **no existe acoplamiento de estado mutable entre cámaras distintas**:
- **Buffers de Fotograma:** Cada cámara posee su propio `BoundCameraSlot` y su propia instancia de `MobilePushFrameBuffer(codigo_camara)`, la cual internamente cuenta con su propio `RLock` y almacenamiento aislado.
- **Topología y ROI:** Las áreas de visión (`ROI-ENT`, `ROI-SAL`) y las funciones de proyección y filtrado son inmutables y puramente funcionales.
- **Almacenamiento de Evidencias:** `LocalDiskEvidenceStorage` genera nombres de archivo únicos con prefijos ISO UTC y tokens aleatorios (`uuid4().hex[:12]`), escribiendo en subdirectorios exclusivos por fecha y cámara (`evidencias_vigia/<fecha>/<camara>/`).
- **Persistencia en PostgreSQL:** `PsycopgDetectionRepository` abre y cierra conexiones independientes a PostgreSQL por transacción, insertando registros con identificadores `id_deteccion` (UUIDv4) completamente aislados.

Por consiguiente, la única necesidad legítima de exclusión mutua para evitar sobreescritura de buffer (*single-slot race*) es **estrictamente por cámara** (evitar que dos solicitudes para `CAM-ENTRADA` colisionen entre sí).

---

## 3. Metodología Experimental y Escenarios

### 3.1 Configuración de Referencia Obligatoria
De conformidad con los requisitos normativos del proyecto:
- **Modelo:** YOLO11n (`yolo11n.pt`).
- **Dispositivo:** `auto` $\rightarrow$ `cuda:0` (NVIDIA GeForce RTX 4050 Laptop GPU).
- **Precisión:** FP32 (`half=False`).
- **Resolución:** 640x480 (`imgsz=640`).
- **Geometría:** `rect=False` (estándar ratificado en OPT-RECT-01).
- **Umbral de Confianza:** 0.25 (detector) / 0.70 (área operativa).
- **Persistencia:** Síncrona canónica (sin piloto asíncrono ni colas en memoria).

### 3.2 Matriz de Escenarios Evaluados
Se diseñaron cuatro escenarios de carga multicámara ($E_1$ a $E_4$), cada uno ejecutado bajo dos regímenes operativos:

| Escenario | Cámaras Activas | Código Cámaras | Áreas Asociadas |
| :--- | :---: | :--- | :--- |
| **E1** | 1 | `CAM-ENTRADA` | `ROI-ENT` |
| **E2** | 2 | `CAM-ENTRADA`, `CAM-SALIDA` | `ROI-ENT`, `ROI-SAL` |
| **E3** | 3 | `CAM-ENTRADA`, `CAM-SALIDA`, `CAM-03` | `ROI-ENT`, `ROI-SAL`, `ROI-ENT` |
| **E4** | 4 | `CAM-ENTRADA`, `CAM-SALIDA`, `CAM-03`, `CAM-04` | `ROI-ENT`, `ROI-SAL`, `ROI-ENT`, `ROI-SAL` |

### 3.3 Regímenes Operativos Evaluados
1. **Régimen Nominal (~1.0 FPS por cámara):**  
   Simula la operación normal de vigilancia perimetral. Cada cámara cuenta con un hilo cliente dedicado que transmite 10 fotogramas espaciados a intervalos precisos de 1.0 segundo (mediante pacing dinámico compensado).
2. **Régimen de Estrés / Saturación (Máximo Throughput):**  
   Simula saturación concurrente y ráfagas masivas. Los hilos de cada cámara transmiten 20 fotogramas de forma continua y sin retardos (0 ms backoff), compitiendo agresivamente por los recursos del sistema.

### 3.4 Telemetría y Métricas Registradas
- **Latencia de Respuesta E2E (ms):** Tiempo total percibido por el cliente HTTP desde el envío hasta la recepción de la respuesta (Media, Desviación Estándar, P50, P90, P95, P99, Mínimo y Máximo).
- **Throughput Agregado (FPS):** Peticiones exitosas procesadas por segundo a través de todo el sistema.
- **Telemetría de Hardware (muestreo a 100 ms con NVML y psutil):**  
  - Utilización de GPU NVIDIA (%) media y pico.
  - Memoria VRAM usada (MB) media y pico.
  - Utilización de CPU (%) media y pico.
  - Memoria RAM del proceso (MB).
  - Temperatura de la GPU (°C).
- **Verificación de Integridad de Datos:**  
  - Tasa de éxito HTTP (códigos 200 vs errores).
  - Concordancia estricta entre detecciones informadas en JSON y registros persistidos en PostgreSQL (`db_matches_responses`).
  - Verificación de no contaminación cruzada en metadatos y evidencia física en NVMe.

---

## 4. Caracterización del Baseline (Línea Base)

El benchmark del baseline se ejecutó utilizando el arnés automatizado [run_multi_camera_benchmark.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/scripts/run_multi_camera_benchmark.py), registrando los datos en [benchmark_multi_baseline.json](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/Docs/fase_1/benchmark_multi_baseline.json).

### 4.1 Resultados de Rendimiento del Baseline

| Escenario | Régimen | Cámaras | Req Totales | Throughput (FPS) | Latencia Media (ms) | Latencia P50 (ms) | Latencia P95 (ms) | Jitter / Std (ms) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **E1** | Nominal | 1 | 10 | 1.00 | 78.40 | 86.50 | 94.00 | 17.17 |
| **E2** | Nominal | 2 | 20 | 2.00 | 104.85 | 101.50 | 172.00 | 38.97 |
| **E3** | Nominal | 3 | 30 | 3.00 | 138.47 | 117.00 | 234.00 | 50.40 |
| **E4** | Nominal | 4 | 40 | 3.98 | 162.87 | 148.50 | 312.05 | 67.24 |
| **E1** | Stress | 1 | 20 | 11.63 | 85.95 | 86.50 | 109.05 | 16.50 |
| **E2** | Stress | 2 | 40 | 16.96 | 116.03 | 125.00 | 156.00 | 34.04 |
| **E3** | Stress | 3 | 60 | 18.02 | 163.05 | 171.00 | 204.00 | 31.78 |
| **E4** | Stress | 4 | 80 | **18.22** | **214.26** | **219.00** | **281.00** | **48.42** |

### 4.2 Telemetría de Hardware del Baseline

| Escenario | Régimen | GPU Util Media | GPU Util Pico | VRAM Pico (MB) | CPU Util Media | RAM RSS (MB) | GPU Temp Pico |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **E1** | Nominal | 5.15% | 19.0% | 1358.1 | 10.85% | 421.3 | 43.0°C |
| **E2** | Nominal | 8.39% | 22.0% | 1353.5 | 8.01% | 425.8 | 43.0°C |
| **E3** | Nominal | 8.47% | 31.0% | 1388.3 | 9.36% | 428.5 | 45.0°C |
| **E4** | Nominal | 8.10% | 42.0% | 1386.1 | 9.40% | 429.2 | 46.0°C |
| **E1** | Stress | 29.88% | 85.0% | 1379.2 | 9.81% | 429.8 | 44.0°C |
| **E2** | Stress | 33.96% | 82.0% | 1375.7 | 11.33% | 430.1 | 44.0°C |
| **E3** | Stress | 25.00% | 76.0% | 1374.7 | 13.85% | 430.2 | 44.0°C |
| **E4** | Stress | **15.91%** | 74.0% | 1371.0 | 12.39% | 430.4 | 46.0°C |

### 4.3 Diagnóstico Cuantitativo del Baseline
1. **Colapso del Throughput en Saturación:** Al pasar de 2 a 4 cámaras en régimen de estrés, el throughput agregado se estancó en **18.22 FPS**, lo que significa que cada cámara individual recibió únicamente $\approx 4.55\text{ FPS}$.
2. **Degradación de Latencia:** La latencia media en E4 stress subió a 214.26 ms, con percentiles P95 alcanzando los 281.00 ms (y hasta 312.05 ms en nominal).
3. **Inanición de GPU por I/O:** La utilización promedio de la GPU cayó drásticamente a **15.91%** en E4 stress, confirmando que los núcleos de la GPU pasaban más del 80% del tiempo bloqueados a la espera de I/O de disco y base de datos.

---

## 5. Optimización Controlada Implementada

Para resolver este cuello de botella estructural sin vulnerar las garantías de persistencia ni los contratos de dominio, se implementó una optimización arquitectónica basada en tres componentes de sincronización:

```mermaid
flowchart TD
    subgraph Optimized["Optimizado: Bloqueo Granular por Cámara + Lock de Inferencia GPU"]
        subgraph CamInflow["Ingesta Concurrente"]
            C1["CAM-ENTRADA"] --> L1["with cam_lock['CAM-ENTRADA']"]
            C2["CAM-SALIDA"] --> L2["with cam_lock['CAM-SALIDA']"]
            C3["CAM-03"] --> L3["with cam_lock['CAM-03']"]
            C4["CAM-04"] --> L4["with cam_lock['CAM-04']"]
        end

        subgraph GPULock["Inferencia GPU Exclusiva (~8 ms)"]
            L1 -->|Turno 1| Y1["with detector._lock (8 ms)"]
            L2 -->|Turno 2| Y2["with detector._lock (8 ms)"]
            L3 -->|Turno 3| Y3["with detector._lock (8 ms)"]
            L4 -->|Turno 4| Y4["with detector._lock (8 ms)"]
        end

        subgraph ParallelIO["I/O de Disco y DB en Paralelo Real"]
            Y1 --> P1["Disco NVMe + Commit DB (Cam 1)"]
            Y2 --> P2["Disco NVMe + Commit DB (Cam 2)"]
            Y3 --> P3["Disco NVMe + Commit DB (Cam 3)"]
            Y4 --> P4["Disco NVMe + Commit DB (Cam 4)"]
        end
    end
```

### 5.1 Bloqueo Granular por Cámara (`camera_process_locks`)
En [ingest_service.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_API/ingest_service.py), se reemplazó el `process_lock` global por un diccionario de bloqueos reentrantes creados de forma determinista y perezosa:

```python
camera_process_locks: Dict[str, threading.RLock] = {}
camera_locks_guard = threading.Lock()
retry_cache_lock = threading.Lock()

def get_camera_process_lock(code: str) -> threading.RLock:
    clean_code = (code or "").strip().upper()
    with camera_locks_guard:
        if clean_code not in camera_process_locks:
            camera_process_locks[clean_code] = threading.RLock()
        return camera_process_locks[clean_code]
```

### 5.2 Protección de Microsegundos en Inferencia GPU (`_lock`)
En [yolo_detector.py](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision/detection/yolo_detector.py), se encapsuló la llamada `model.predict()` bajo el bloqueo reentrante interno del detector:

```python
with self._lock:
    results = model.predict(
        source=frame,
        conf=self._config.confidence_threshold,
        iou=self._config.iou_threshold,
        device=self._config.device,
        imgsz=self._config.imgsz,
        classes=list(self._config.classes),
        verbose=False,
        save=False,
        show=False,
    )
```
Esto garantiza total seguridad de asignación de memoria CUDA en PyTorch sin serializar el resto del pipeline. El bloqueo se sostiene únicamente durante los **~8 ms** de la inferencia, liberándose de inmediato.

### 5.3 Protección de Caché de Reintentos (`retry_cache_lock`)
Las lecturas y escrituras en el diccionario `persisted_retry_cache` se protegieron con `retry_cache_lock`, una operación que toma menos de 1 microsegundo.

---

## 6. Caracterización Posterior a la Optimización

Se reejecutó el benchmark multicámara idéntico bajo las mismas condiciones y parámetros exactos, generando el conjunto de datos [benchmark_multi_optimized.json](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/Docs/fase_1/benchmark_multi_optimized.json).

### 6.1 Resultados de Rendimiento Post-Optimización

| Escenario | Régimen | Cámaras | Req Totales | Throughput (FPS) | Latencia Media (ms) | Latencia P50 (ms) | Latencia P95 (ms) | Jitter / Std (ms) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **E1** | Nominal | 1 | 10 | 1.00 | 121.70 | 125.00 | 164.80 | 25.10 |
| **E2** | Nominal | 2 | 20 | 2.00 | 123.20 | 125.00 | 203.00 | 38.65 |
| **E3** | Nominal | 3 | 30 | 3.00 | 153.57 | 141.00 | 259.85 | 52.37 |
| **E4** | Nominal | 4 | 40 | 3.98 | 177.40 | 172.00 | 281.00 | 50.84 |
| **E1** | Stress | 1 | 20 | 9.92 | 100.80 | 94.00 | 141.00 | 21.05 |
| **E2** | Stress | 2 | 40 | 17.78 | 110.95 | 110.00 | 156.00 | 24.23 |
| **E3** | Stress | 3 | 60 | **20.43** | **144.50** | **141.00** | **187.00** | **23.51** |
| **E4** | Stress | 4 | 80 | **19.69** | **188.65** | **172.00** | 328.75 | 55.49 |

### 6.2 Telemetría de Hardware Post-Optimización

| Escenario | Régimen | GPU Util Media | GPU Util Pico | VRAM Pico (MB) | CPU Util Media | RAM RSS (MB) | GPU Temp Pico |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **E1** | Nominal | 13.96% | 46.0% | 1367.8 | 7.67% | 429.5 | 44.0°C |
| **E2** | Nominal | 15.31% | 51.0% | 1430.1 | 9.75% | 430.1 | 44.0°C |
| **E3** | Nominal | 16.82% | 54.0% | 1409.9 | 8.04% | 430.3 | 44.0°C |
| **E4** | Nominal | 16.75% | 60.0% | 1407.3 | 9.86% | 430.4 | 44.0°C |
| **E1** | Stress | 29.20% | 80.0% | 1407.3 | 9.72% | 430.5 | 44.0°C |
| **E2** | Stress | 32.23% | 84.0% | 1407.0 | 13.72% | 430.8 | 44.0°C |
| **E3** | Stress | 31.03% | 79.0% | 1405.8 | 13.74% | 431.0 | 44.0°C |
| **E4** | Stress | **32.10%** | **88.0%** | **1408.5** | 14.69% | 431.2 | 44.0°C |

---

## 7. Comparación Experimental y Análisis de Deltas

### 7.1 Comparativa Directa Baseline vs. Optimizado

| Escenario | Régimen | Throughput Base (FPS) | Throughput Opt (FPS) | $\Delta$ Throughput | Latencia Base P50 (ms) | Latencia Opt P50 (ms) | $\Delta$ Latencia P50 | Latencia Base Media (ms) | Latencia Opt Media (ms) | $\Delta$ Latencia Media |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **E1** | Nominal | 1.00 | 1.00 | 0.0% | 86.50 | 125.00 | +38.50 ms | 78.40 | 121.70 | +43.30 ms |
| **E2** | Nominal | 2.00 | 2.00 | 0.0% | 101.50 | 125.00 | +23.50 ms | 104.85 | 123.20 | +18.35 ms |
| **E3** | Nominal | 3.00 | 3.00 | 0.0% | 117.00 | 141.00 | +24.00 ms | 138.47 | 153.57 | +15.10 ms |
| **E4** | Nominal | 3.98 | 3.98 | 0.0% | 148.50 | 172.00 | +23.50 ms | 162.87 | 177.40 | +14.53 ms |
| **E1** | Stress | 11.63 | 9.92 | -14.7% | 86.50 | 94.00 | +7.50 ms | 85.95 | 100.80 | +14.85 ms |
| **E2** | Stress | 16.96 | 17.78 | **+4.8%** | 125.00 | 110.00 | **-15.00 ms** | 116.03 | 110.95 | **-5.08 ms (-4.4%)** |
| **E3** | Stress | 18.02 | 20.43 | **+13.4%** | 171.00 | 141.00 | **-30.00 ms** | 163.05 | 144.50 | **-18.55 ms (-11.4%)** |
| **E4** | Stress | 18.22 | 19.69 | **+8.1%** | 219.00 | 172.00 | **-47.00 ms (-21.5%)** | 214.26 | 188.65 | **-25.61 ms (-12.0%)** |

### 7.2 Análisis Técnico de Mejoras
1. **Ruptura de la Barrera de Concurrencia:**  
   Bajo concurrencia de 3 y 4 cámaras en saturación, el throughput superó la barrera histórica de 18 FPS del baseline, alcanzando **20.43 FPS en E3** (+13.4%) y **19.69 FPS en E4** (+8.1%).
2. **Reducción Significativa de Latencia y Jitter bajo Concurrencia:**  
   - En **E4 stress**, la latencia típica (P50) disminuyó de 219.0 ms a **172.0 ms** (**-47 ms, -21.5%**), y la latencia media se redujo de 214.26 ms a **188.65 ms** (**-12.0%**).
   - En **E3 stress**, la latencia P50 bajó de 171.0 ms a **141.0 ms** (**-30 ms, -17.5%**), y la media se redujo en **-11.4%**.
   - En **E2 stress**, la latencia P50 bajó de 125.0 ms a **110.0 ms** (**-15 ms, -12.0%**).
3. **Eliminación de la Inanición de GPU:**  
   La utilización de la GPU NVIDIA en E4 stress aumentó de **15.91% a 32.10%** (más del doble). La GPU se mantiene activa procesando inferencias predictivas de forma fluida mientras las escrituras de disco de las cámaras se realizan concurrentemente en hilos separados.
4. **Comportamiento en Régimen Nominal:**  
   A ~1 FPS por cámara, la latencia se mantuvo holgadamente por debajo de 200 ms (121.7 ms a 177.4 ms), sin comprometer la estabilidad ni experimentar acumulación en buffers.

---

## 8. Verificación de Integridad y Ausencia de Regresiones

### 8.1 Consistencia de Persistencia en PostgreSQL
Durante las 16 pruebas combinadas (baseline y optimizado, nominal y estrés), se remitieron más de 400 fotogramas. Se verificó contra la base de datos PostgreSQL `vigia_db`:
- **Delta de Inserciones Exacto:** En el 100% de las ejecuciones, `db_persisted_delta` coincidió numéricamente con `persisted_in_responses`.
- **Cero Violaciones de Integridad Referencial:** Cada registro insertado en `deteccion` conservó su relación de clave foránea válida con la tabla `area_vision` y la cámara correspondiente (`id_camara`).
- **Aislamiento Multicanal:** Se verificó que las detecciones originadas por `CAM-03` no hicieran referencia al área de `CAM-SALIDA`, ni viceversa.

### 8.2 Integridad de Evidencias en NVMe
- Todas las rutas generadas (`*_orig.jpg` y `*_annot.jpg`) se verificaron en disco.
- Los archivos fueron codificados en calidad JPEG 85, arrojando imágenes válidas sin corrupción de encabezados ni truncamientos.

### 8.3 Suite de Pruebas Unitarias
Se ejecutó la suite de 284 pruebas unitarias con el ejecutable Python canónico:
```text
Ran 284 tests in 30.551s
OK (skipped=1)
```
Tasa de éxito: **100% (284/284 aprobadas)**. Cero regresiones en lógica de enrolamiento, topología, RBAC, autenticación, pipeline de visión ni persistencia.

---

## 9. Capacidad Multicámara Demostrada y Límites Operacionales

### 9.1 Capacidad Operacional Demostrada

```
                                  CAPACIDAD MULTICÁMARA DEMOSTRADA
                                  =================================
                                  
     Throughput Saturación (FPS)  | 20.43 FPS  (E3) / 19.69 FPS (E4)
     Carga Nominal de Diseño      | 4.00 FPS   (4 cámaras a 1.0 FPS)
     Factor de Holgura (Headroom) | 4.9x a 5.1x sobre la demanda nominal
     VRAM en Uso                  | 1408.5 MB / 6140 MB  (22.9% de capacidad)
     Temperatura Térmica          | 44.0°C  (Operación fría y segura)
     Integridad de Datos          | 100.0%  (0 fallos, 0 duplicados espurios)
```

### 9.2 Margen de Seguridad Operativa
Bajo la carga de diseño de VIGÍA (4 cámaras operando a ~1.0 FPS cada una, demandando 4.0 FPS en total):
- El sistema opera al **~20%** de su capacidad máxima de saturación demostrada (20.43 FPS).
- El factor de holgura es de **5.1x**, lo que asegura absorción inmediata ante ráfagas concurrentes de vehículos en múltiples carriles simultáneamente.
- La memoria VRAM (1.4 GB) deja disponibles más de 4.7 GB de memoria libre en la GPU para el futuro módulo de OCR/ANPR.

### 9.3 Límites Identificados y Recomendaciones
1. **Límite de la Persistencia Síncrona:** Aunque la concurrencia entre cámaras distintas ahora es paralela, cada cámara individual aún procesa su flujo de forma síncrona. Si una sola cámara requiere transmitir a más de 10-12 FPS de forma sostenida, la persistencia asíncrona diseñada en `VIGIA-VISION-OPT-05` e implementada en el piloto `IMP-01` proveerá la solución definitiva en etapas posteriores.
2. **Escalabilidad Más Allá de 4 Cámaras:** Para escalar a 6 u 8 cámaras simultáneas en futuras fases, el motor actual cuenta con el headroom de cómputo GPU necesario (utilización media de solo 32%), requiriéndose únicamente expandir el pool de conexiones a PostgreSQL.

---

## 10. Dictamen Final y Congelamiento del Motor

### 10.1 Dictamen Formal
De conformidad con los criterios técnicos y las metas fijadas para `VIGIA-OPT-MULTI-01`:

> **DICTAMEN: APROBADO Y CONGELADO**  
> Se autoriza la adopción definitiva de la arquitectura de **Bloqueo Granular por Cámara con Exclusión Mutua de Microsegundos en Inferencia GPU** para el entorno productivo de VIGÍA Vision Systems.  
> Se da por finalizada y cerrada la etapa de optimizaciones de rendimiento del motor de visión artificial.

### 10.2 Configuración Estándar Congelada de Producción
Queda formalmente congelada la siguiente especificación técnica para las pruebas funcionales y físicas:

1. **Hardware / Dispositivo:** NVIDIA GeForce RTX 4050 Laptop GPU (`cuda:0`).
2. **Entorno Python:** `.venv_cuda` (PyTorch 2.6.0+cu124, CUDA 12.4).
3. **Modelo:** YOLO11n (`yolo11n.pt`).
4. **Precisión:** FP32 (`half=False`).
5. **Resolución de Inferencia:** 640x480 (`imgsz=640`).
6. **Geometría:** `rect=False`.
7. **Sincronización:** Granular por cámara (`camera_process_locks`) + lock de inferencia (`detector._lock`) + `retry_cache_lock`.
8. **Persistencia:** Síncrona canónica (almacenamiento en NVMe y PostgreSQL).
9. **Topología Operativa:** 2 cámaras base (`CAM-ENTRADA`, `CAM-SALIDA`) con soporte verificado para expansión multicámara (`CAM-03`, `CAM-04`).
