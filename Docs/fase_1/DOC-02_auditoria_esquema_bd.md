# DOC-02. Auditoría de Compatibilidad del Esquema PostgreSQL con V1

## 1. Control Documental
* **Proyecto:** VIGÍA Vision Systems
* **Documento:** DOC-02 — Auditoría de Compatibilidad del Esquema SQL con V1
* **Fase:** Fase 1 — Especificación Formal y Auditoría de Datos
* **Estado:** Propuesta Técnica de Auditoría (Conclusión Provisional para Revisión Humana)
* **Versión:** 1.0.0
* **Fecha:** 27 de octubre de 2026
* **Autor:** Arquitectura de Software VIGÍA & Especialista en PostgreSQL

---

## 2. Objetivo y Metodología
Determinar con precisión técnica si el esquema relacional existente en PostgreSQL (definido en las migraciones de la línea base V1) permite soportar los requisitos funcionales, contratos de dominio y necesidades de persistencia de la versión V1 sin requerir modificaciones DDL ni nuevas migraciones de base de datos.

La auditoría se apoya exclusivamente en la inspección de archivos reales del repositorio:
1. `BD/migrations/V000__init_database.sql`
2. `BD/migrations/V001__baseline_schema.sql`
3. `BD/migrations/V002__triggers.sql`
4. `BD/migrations/V003__seed_data.sql`
5. `Docs/fase_1/DOC-01_modelos_dominio.md`
6. `VIGIA_Core/domain/vision_result.py`
7. `VIGIA_Core/domain/access_decision.py`
8. `VR_Semaforo/vision/processor.py` y `VR_Semaforo/database.py`

---

## 3. Verificación Exhaustiva de Tablas del DDL V1

### 3.1. Tabla `camara`
*Evidencia:* `BD/migrations/V001__baseline_schema.sql`, líneas 267–297.

* **Estructura Declarativa:**
  * `id_camara UUID PRIMARY KEY DEFAULT gen_random_uuid()`
  * `codigo VARCHAR(30) NOT NULL UNIQUE`
  * `nombre VARCHAR(100) NOT NULL`
  * `uri_stream TEXT NOT NULL`
  * `resolucion_ancho INTEGER NULL`
  * `resolucion_alto INTEGER NULL`
  * `activa BOOLEAN NOT NULL DEFAULT TRUE`
  * `creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP`
* **Restricciones Declarativas:**
  * `ck_camara_codigo`: `CHECK (codigo = BTRIM(codigo) AND codigo <> '')`
  * `ck_camara_nombre`: `CHECK (nombre = BTRIM(nombre) AND nombre <> '')`
  * `ck_camara_uri`: `CHECK (uri_stream = BTRIM(uri_stream) AND uri_stream <> '')`
  * `ck_camara_resolucion`: `CHECK ((resolucion_ancho IS NULL AND resolucion_alto IS NULL) OR (resolucion_ancho > 0 AND resolucion_alto > 0))`
* **Análisis de Compatibilidad:**
  * [HECHO VERIFICADO]: La tabla permite almacenar los registros correspondientes a las cámaras funcionales `CAM-ENTRADA` y `CAM-SALIDA`, con nombres descriptivos y cualquier URI de captura válida (`rtsp://...`, descriptor USB o URL HTTP).
  * [HECHO VERIFICADO]: **El DDL no obliga a registrar exactamente dos cámaras**. No existe ninguna restricción SQL que limite la tabla a dos filas ni que exija los códigos específicos. La condición de tener exactamente dos cámaras físicas es una **regla funcional de la aplicación**.

---

### 3.2. Tabla `area_vision`
*Evidencia:* `BD/migrations/V001__baseline_schema.sql`, líneas 307–344.

* **Estructura Declarativa:**
  * `id_area_vision UUID PRIMARY KEY DEFAULT gen_random_uuid()`
  * `id_camara UUID NOT NULL` (FK a `camara(id_camara)` con `ON DELETE RESTRICT`)
  * `codigo VARCHAR(30) NOT NULL`
  * `nombre VARCHAR(100) NOT NULL`
  * `tipo_movimiento VARCHAR(10) NOT NULL`
  * `x_min NUMERIC(4,3) NOT NULL`
  * `y_min NUMERIC(4,3) NOT NULL`
  * `x_max NUMERIC(4,3) NOT NULL`
  * `y_max NUMERIC(4,3) NOT NULL`
  * `activa BOOLEAN NOT NULL DEFAULT TRUE`
  * `creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP`
* **Restricciones Declarativas:**
  * `uq_area_vision_camara_codigo`: `UNIQUE (id_camara, codigo)`
  * `ck_area_vision_tipo_movimiento`: `CHECK (tipo_movimiento IN ('ENTRADA', 'SALIDA'))`
  * `ck_area_vision_coordenadas`: `CHECK (x_min >= 0 AND x_min < x_max AND x_max <= 1 AND y_min >= 0 AND y_min < y_max AND y_max <= 1)`
* **Análisis de Compatibilidad frente a las Reglas Funcionales de DOC-01:**
  1. *Exactamente dos cámaras registradas para la operación:* **No impuesta por DDL**. La tabla `camara` admite $0 \dots N$ filas. *(Requiere validación de aplicación).*
  2. *Exactamente dos áreas operativas activas en el sistema:* **No impuesta por DDL**. La tabla `area_vision` admite $0 \dots N$ filas. *(Requiere validación de aplicación).*
  3. *Una sola área operativa activa por cámara:* **No impuesta por DDL**. La restricción `UNIQUE (id_camara, codigo)` solo evita códigos idénticos dentro de la misma cámara, pero permite múltiples áreas activas para una cámara en SQL. *(Requiere validación de aplicación).*
  4. *Área de `CAM-ENTRADA` con `tipo_movimiento = 'ENTRADA'`:* **No impuesta por DDL**. El CHECK solo valida que el valor sea `'ENTRADA'` o `'SALIDA'`, pero no qué cámara lo porta. *(Requiere validación de aplicación).*
  5. *Área de `CAM-SALIDA` con `tipo_movimiento = 'SALIDA'`:* **No impuesta por DDL**. *(Requiere validación de aplicación).*

---

### 3.3. Tabla `deteccion`
*Evidencia:* `BD/migrations/V001__baseline_schema.sql`, líneas 350–401.

* **Estructura Declarativa:**
  * `id_deteccion UUID PRIMARY KEY DEFAULT gen_random_uuid()`
  * `id_area_vision UUID NOT NULL` (FK a `area_vision(id_area_vision)` con `ON DELETE RESTRICT`)
  * `fecha_hora TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP`
  * `placa_detectada VARCHAR(20) NULL`
  * `confianza_placa NUMERIC(4,3) NULL`
  * `confianza_vehiculo NUMERIC(4,3) NULL`
  * `tipo_vehiculo_pred VARCHAR(20) NULL`
  * `ruta_evidencia_foto TEXT NULL`
* **Restricciones Declarativas:**
  * `ck_deteccion_placa`:
    ```sql
    CHECK (
        placa_detectada IS NULL
        OR (
            placa_detectada = UPPER(BTRIM(placa_detectada))
            AND placa_detectada !~ '[[:space:]-]'
            AND placa_detectada <> ''
        )
    )
    ```
  * `ck_deteccion_confianza_placa`: `CHECK (confianza_placa IS NULL OR confianza_placa BETWEEN 0 AND 1)`
  * `ck_deteccion_confianza_vehiculo`: `CHECK (confianza_vehiculo IS NULL OR confianza_vehiculo BETWEEN 0 AND 1)`
  * `ck_deteccion_tipo_vehiculo`:
    ```sql
    CHECK (
        tipo_vehiculo_pred IS NULL
        OR tipo_vehiculo_pred IN (
            'AUTOMOVIL',
            'CAMIONETA',
            'CAMION',
            'MOTOCICLETA',
            'OTRO'
        )
    )
    ```
  * `ck_deteccion_evidencia`:
    ```sql
    CHECK (
        ruta_evidencia_foto IS NULL
        OR (
            ruta_evidencia_foto = BTRIM(ruta_evidencia_foto)
            AND ruta_evidencia_foto <> ''
        )
    )
    ```
* **Análisis de Casos de Placa:**
  * *Ausencia de placa o placa no localizada:* Totalmente compatible (`placa_detectada = NULL`, `confianza_placa = NULL`).
  * *Placa ilegible:* Totalmente compatible (`placa_detectada = NULL`, `confianza_placa = NULL`).
  * *Placa legible:* Compatible siempre que el valor cumpla con la restricción `ck_deteccion_placa`.

---

## 4. Análisis de Puntos Críticos de Integración

### 4.1. Normalización de Matrículas y Restricción SQL
* **La Restricción SQL:** Exige que `placa_detectada` esté en mayúsculas, sin espacios al inicio/final, no sea vacía y **no contenga espacios internos ni guiones** (`!~ '[[:space:]-]'`).
* **Riesgos de Eliminación Indiscriminada de Caracteres:**
  * La aplicación no debe ejecutar un reemplazo a ciegas (`.replace("-", "").replace(" ", "")`) como si fuera una regla aprobada y universal.
  * Ciertas matrículas internacionales o formatos institucionales específicos podrían verse truncados o adulterados si se suprimen caracteres sin una regla formal de negocio.
* **Diferenciación Requerida:**
  * *Texto Original Reconocido por OCR:* Es la cadena directa emitida por el modelo OCR (puede incluir guiones, espacios o caracteres ambiguos). El DDL actual **no posee una columna separada para almacenar el texto crudo original**.
  * *Valor Normalizado para Persistencia:* Es el texto validado y ajustado al formato admitido por la columna `placa_detectada`.
* **Acción Requerida:** La aplicación debe validar formalmente el formato antes de persistir. Si el texto no es normalizable bajo las reglas que se aprueben, debe persistirse como `placa_detectada = NULL` y registrarse la observación correspondiente.

### 4.2. Discrepancia en el Catálogo de Vehículos (`AUTOBUS` vs. `OTRO`)
* **Evidencia en Contrato:** En `VIGIA_Core/domain/vision_result.py` (línea 66), el docstring menciona como valores esperados: `'AUTOMOVIL'`, `'CAMIONETA'`, `'MOTOCICLETA'`, `'AUTOBUS'`, `'CAMION'`.
* **Evidencia en DDL:** En `BD/migrations/V001__baseline_schema.sql` (líneas 384–391), la restricción `ck_deteccion_tipo_vehiculo` solo admite: `'AUTOMOVIL'`, `'CAMIONETA'`, `'CAMION'`, `'MOTOCICLETA'`, `'OTRO'`.
* **Evidencia en Modelo de Inferencia:** En `VR_Semaforo/vision/processor.py` (líneas 50–52), YOLO filtra las clases COCO `[2, 3, 5, 7]` correspondientes a `car`, `motorcycle`, `bus`, `truck`. En el prototipo actual, esta salida solo se usa para conteo numérico (`contar_carritos`), sin mapeo categórico formal hacia la base de datos.
* **Decisión Pendiente:** Queda pendiente de definición funcional si:
  a) La aplicación mapea la clase `bus` hacia `'CAMION'` u `'OTRO'` antes de insertar en `deteccion`.
  b) Se amplía formalmente el CHECK constraint en una migración futura para incorporar `'AUTOBUS'`.

### 4.3. Persistencia de Fotografías y Gestión de Fallos Parciales
* **Estado Real del Código:**
  * [HECHO VERIFICADO]: `VR_Semaforo/database.py` tiene 0 bytes. **No existe código implementado de inserción relacional en PostgreSQL**.
  * [HECHO VERIFICADO]: En `VR_Semaforo/vision/processor.py` solo se guardan imágenes dudosas en disco local (`dataset_dudoso/`) cuando la confianza cae en $[0.20, 0.50)$. No existe guardado de evidencias para detecciones generales.
* **Ausencia de Atomicidad:** No existe transacción atómica (2PC) nativa entre el sistema de archivos del sistema operativo y PostgreSQL.
* **Manejo de los Dos Modos de Fallo Parcial:**
  1. *Fallo 1: Error al escribir el archivo en disco (disco lleno, fallo de E/S).*  
     *Política acordada:* La aplicación captura la excepción, registra el error técnico en logs y persiste la fila en `deteccion` con `ruta_evidencia_foto = NULL`. No se debe registrar una ruta inexistente ni dar por asegurada la evidencia.
  2. *Fallo 2: Fotografía guardada correctamente en disco, pero el `INSERT` en PostgreSQL falla (error de conexión, violación de restricción).*  
     *Problema:* Se genera un archivo huérfano en disco sin registro asociado en la base de datos.  
     *Propuesta de compensación/reconciliación:* Diseñar un mecanismo en la capa repository que, ante el fallo del `INSERT`, intente eliminar el archivo recién creado o lo marque en una bitácora temporal de reconciliación para su depuración posterior. **Se documenta expresamente que dicha solución no está implementada actualmente**.

### 4.4. Mapeo de Estados de Visión hacia la Tabla `deteccion`
* [HECHO VERIFICADO]: La tabla `deteccion` **no posee columna `status` ni está diseñada para almacenar fallos técnicos o fotogramas vacíos**.
* **Criterio de Persistencia por Estado de `VisionResult`:**
  * `VEHICLE_DETECTED_PLATE_READ`: **Se persiste en `deteccion`** (vehículo presente y placa leída).
  * `VEHICLE_DETECTED_PLATE_UNREADABLE`: **Se persiste en `deteccion`** (vehículo presente, `placa_detectada = NULL`).
  * `VEHICLE_DETECTED_NO_PLATE`: **Se persiste en `deteccion`** (vehículo presente, `placa_detectada = NULL`).
  * `NO_VEHICLE_DETECTED`: **NO se persiste en `deteccion`** (no hay evento vehicular que auditar).
  * `CAMERA_ERROR`: **NO se persiste en `deteccion`** (fallo de captura de hardware; no debe registrarse como detección vehicular).
  * `VISION_ERROR`: **NO se persiste en `deteccion`** (excepción del modelo; se reporta al Core y logs de aplicación).

---

## 5. Matriz de Compatibilidad: Esquema DDL vs. Requisitos V1

| Requisito / Regla Funcional | Evidencia en DDL o Código | Estado de Compatibilidad | Acción Recomendada | ¿Requiere Migración SQL? |
| :--- | :--- | :---: | :--- | :---: |
| **Identificación de 2 Cámaras (`CAM-ENTRADA`, `CAM-SALIDA`)** | `camara.codigo VARCHAR(30) UNIQUE NOT NULL` (`V001__baseline_schema.sql`, L269). | **COMPATIBLE CON REGLA DE APLICACIÓN** | El servicio de configuración en la aplicación debe validar que existan exactamente las 2 cámaras. | **No** |
| **Configuración de Exactamente 2 Áreas Operativas Activas** | `area_vision.activa BOOLEAN DEFAULT TRUE` (`V001__baseline_schema.sql`, L317). | **COMPATIBLE CON REGLA DE APLICACIÓN** | La aplicación debe validar que el número total de áreas activas sea exactamente dos. | **No** |
| **Asociación 1:1 entre Cámara y Área Activa** | `area_vision.id_camara` es FK sin UNIQUE (`V001__baseline_schema.sql`, L309). | **COMPATIBLE CON REGLA DE APLICACIÓN** | La aplicación debe validar que cada cámara tenga una sola área con `activa = TRUE`. | **No** |
| **Área Entrada asociada a Movimiento `ENTRADA`** | `CHECK (tipo_movimiento IN ('ENTRADA', 'SALIDA'))` (`V001__baseline_schema.sql`, L330). | **COMPATIBLE CON REGLA DE APLICACIÓN** | La aplicación debe verificar que el área de `CAM-ENTRADA` tenga `tipo_movimiento = 'ENTRADA'`. | **No** |
| **Área Salida asociada a Movimiento `SALIDA`** | `CHECK (tipo_movimiento IN ('ENTRADA', 'SALIDA'))` (`V001__baseline_schema.sql`, L330). | **COMPATIBLE CON REGLA DE APLICACIÓN** | La aplicación debe verificar que el área de `CAM-SALIDA` tenga `tipo_movimiento = 'SALIDA'`. | **No** |
| **Coordenadas Normalizadas ROI $[0, 1]$** | `CHECK (x_min >= 0 AND x_max <= 1 ...)` (`V001__baseline_schema.sql`, L331-336). | **COMPATIBLE** | Respaldado plenamente por las restricciones CHECK declarativas del DDL. | **No** |
| **Persistencia de Detecciones Vehiculares** | Columnas y tipos en tabla `deteccion` (`V001__baseline_schema.sql`, L350-401). | **COMPATIBLE** | Implementar la capa repository en `VIGIA_Vision` para ejecutar los `INSERT` correspondientes. | **No** |
| **Formato de Matrícula en `deteccion`** | `CHECK (placa_detectada !~ '[[:space:]-]')` (`V001__baseline_schema.sql`, L368). | **COMPATIBLE CON REGLA DE APLICACIÓN** | Validar y normalizar el texto OCR antes del `INSERT`, definiendo las reglas formales de matrícula. | **No** |
| **Clasificación de Tipo de Vehículo** | `CHECK (tipo_vehiculo_pred IN (... 'OTRO'))` (`V001__baseline_schema.sql`, L385-391). | **COMPATIBLE CON REGLA DE APLICACIÓN** | Resolver el mapeo provisional de `AUTOBUS` hacia `'OTRO'` o categoría válida en la aplicación. | **No** |
| **Almacenamiento de Referencia de Fotografía** | `ruta_evidencia_foto TEXT NULL` (`V001__baseline_schema.sql`, L358, 394). | **COMPATIBLE** | Almacenar ruta relativa al archivo; asignar `NULL` ante fallos de escritura física en disco. | **No** |
| **Exclusión de Persistencia de Cuadros Vacíos y Errores** | La tabla `deteccion` no almacena estados de transmisión ni fallos técnicos. | **COMPATIBLE CON REGLA DE APLICACIÓN** | La capa de aplicación omite invocar al repositorio ante `NO_VEHICLE_DETECTED` o errores técnicos. | **No** |

---

## 6. Dictamen Técnico Sustentado

### **Conclusión Provisional:**
> **El esquema relacional actual (`V001__baseline_schema.sql`) soporta la V1 sin requerir nuevas migraciones SQL, sujeto a resolver los contratos de mapeo a nivel de aplicación y completar las pruebas unitarias y de integración correspondientes.**

### **Fundamentos del Dictamen:**
1. **Suficiencia Estructural:** Las tablas `camara`, `area_vision` y `deteccion` poseen todas las columnas, restricciones y tipos de datos necesarios para la operación de la caseta en V1.
2. **Desacoplamiento Saludable:** Las reglas específicas de la topología V1 (exactamente dos cámaras y dos áreas activas) son reglas de configuración que deben residir en la capa de aplicación. Mantenerlas fuera del DDL preserva la capacidad del esquema de evolucionar a topologías multi-carril en versiones posteriores sin modificaciones estructurales.
3. **Condicionantes para la Implementación:**
   * Desarrollar el servicio de validación de configuración inicial de cámaras y áreas.
   * Diseñar la función de normalización y validación previa de matrículas antes de persistir.
   * Establecer el mapeo de categorías vehiculares para evitar rechazos por `ck_deteccion_tipo_vehiculo`.
   * Implementar la persistencia desacoplada con manejo defensivo de errores en disco (`ruta_evidencia_foto = NULL`).

---

## 7. Decisiones Técnicas Pendientes
1. **Resolución Definitiva de `AUTOBUS` vs. `OTRO`:** Decidir formalmente si la ontología de V1 adopta `'OTRO'` como contenedor genérico para vehículos de transporte pesado/pasajeros o si se programará una migración DDL posterior para incluir `'AUTOBUS'`.
2. **Definición de Formatos de Matrícula Admitidos:** Aprobar las expresiones regulares y reglas de negocio para validar placas antes de la inserción.
3. **Mecanismo de Compensación para Archivos Huérfanos:** Diseñar la política de limpieza ante el fallo del `INSERT` en PostgreSQL cuando la imagen ya ha sido escrita en disco.
4. **Umbral de Confianza para Evidencias Relevantes:** Determinar el valor de confianza vehicular a partir del cual se genera fotografía persistente.
