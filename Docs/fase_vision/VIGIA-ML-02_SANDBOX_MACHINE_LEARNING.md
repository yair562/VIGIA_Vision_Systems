# VIGIA-ML-02 — Entorno Experimental de Machine Learning y Reconocimiento de Atributos Vehiculares

**Proyecto:** VIGÍA Vision Systems  
**Fase:** VIGIA-ML-02 (Preparación de Sandbox Aislado, Metodología y Prototipo de Atributos)  
**Fecha de Emisión:** 14 de Noviembre de 2026  
**Responsable Técnico:** Ingeniería VIGÍA  
**Colaborador Académico:** Estudiante de Inteligencia Artificial  
**Alcance:** Creación de sandbox aislado [`experiments/vigia_ml/`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vigia_ml), curación reproducible SHA-256, esquema de anotación manual, Baseline A (HSV + CIELAB), diseño técnico de Baseline B (`SVM` / `Random Forest`), metodología de evaluación y guía académica.

---

## 1. Resumen Ejecutivo y Estado de Preparación

1. **Sandbox 100% aislado:** Se construyó [`experiments/vigia_ml/`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vigia_ml) completamente desacoplado de [`VIGIA_Core`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Core), [`VIGIA_Vision`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Vision), [`VIGIA_API`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_API), [`VIGIA_Dashboard`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/VIGIA_Dashboard), [`yolo11n.pt`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/yolo11n.pt) y PostgreSQL.
2. **Protección estricta de evidencias originales:** Antes de copiar archivos se inspeccionó el espacio libre (`99.38 GB` libres; huella total de [`evidencias_vigia`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/evidencias_vigia) = `127.28 MB` en `604` pares). En lugar de duplicar ciegamente los `604` pares, [`controlled_copy.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vigia_ml/src/dataset/controlled_copy.py) copió únicamente los **87 pares deduplicados** (`174` archivos, `11,522,393` bytes ≈ `10.99 MB`) de `20261111` y `20261114`, verificando **87/87** checksums SHA-256 sin tocar el origen.
3. **Sin declaraciones prematuras de producción:** No se entrenó ningún modelo definitivo ni se integró reconocimiento de color al pipeline productivo. Todo prototipo y métrica permanece en estado **experimental de sandbox**, sujeto a futuras capturas reales `1:1` ([`VIGIA-VISION-03B.1_PROTOCOLO_CAPTURA.md`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/Docs/fase_vision/VIGIA-VISION-03B.1_PROTOCOLO_CAPTURA.md)).

---

## 2. Arquitectura y Estructura del Sandbox

```text
VIGIA_Vision_Systems/
├── Docs/fase_vision/
│   └── VIGIA-ML-02_SANDBOX_MACHINE_LEARNING.md
└── experiments/
    └── vigia_ml/
        ├── README.md
        ├── requirements.txt
        ├── configs/
        │   └── ml_experiment.yaml
        ├── data/
        │   ├── raw/                  # 87 pares deduplicados (174 JPG) + copy_receipt.json
        │   ├── working/              # Espacio de trabajo intermedio del estudiante
        │   ├── annotations/          # schema_v1.json + annotations_v1_template.json
        │   └── processed/            # manifest_v1.* (604) y sandbox_raw_manifest_v1.* (87)
        ├── notebooks/
        │   └── 01_exploracion_y_color_sandbox.ipynb
        ├── src/
        │   ├── dataset/              # inventory.py, controlled_copy.py, annotation_schema.py
        │   ├── preprocessing/        # roi_crop.py
        │   ├── color_analysis/       # baseline_classic.py (Baseline A)
        │   ├── models/               # color_features.py, baseline_ml.py (Baseline B)
        │   └── evaluation/           # splits.py, metrics.py, run_baseline_a_smoke.py
        ├── tests/                    # 4 suites unitarias (9 pruebas pasando)
        ├── reports/                  # GUIA_ACTIVIDADES_ESTUDIANTE_IA.md, METODOLOGIA_EVALUACION_ML.md, smoke JSON
        └── artifacts/                # Reservado para artefactos locales experimentales
```

---

## 3. Inventario, Curación y Copia Controlada (Actividad A)

### 3.1 Herramienta de Inventario ([`inventory.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vigia_ml/src/dataset/inventory.py))
- Ejecución en modo de **solo lectura** sobre `../../evidencias_vigia` (rutas POSIX relativas, cero rutas absolutas de host).
- Genera [`manifest_v1.json`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vigia_ml/data/processed/manifest_v1.json) y [`manifest_v1.csv`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vigia_ml/data/processed/manifest_v1.csv) con todos los campos requeridos (`sample_id`, `image_path`, `sha256`, `capture_timestamp_utc`, `camera_id`, `width`, `height`, `source_domain`, `session_id`, `duplicate_group`, `annotation_status`, `ground_truth_status`) más métricas de calidad (`sharpness_laplacian`, `luminance_mean_y`, `pct_dark`, `pct_glare`, `dhash_hex`, `consecutive_mad`, `pair_complete`, `exact_duplicate_of`).
- **Resultados del inventario global ejecutado:**
  - Registros inventariados: **604** pares históricos (`20261101` a `20261114`).
  - Sesiones temporales (`gap > 60 s`): **29**.
  - Clústeres únicos de similitud perceptual (`MAD < 8` / `dHash <= 6`): **140**.
  - Procedencia explícita (`resolve_source_domain`): `20261111 -> SCREEN_RECAPTURE`, `20261114 -> SCALE_MODEL_LAB`, fechas no auditadas $\to$ `UNKNOWN` (jamás se infiere `REAL_FULL_SCALE` por nombre de archivo ni por YOLO).

### 3.2 Copia Controlada SHA-256 ([`controlled_copy.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vigia_ml/src/dataset/controlled_copy.py))
- Verificación previa de disco (`99.376 GB` libres) y deduplicación por clúster sobre `20261111` y `20261114`:
  - Total escaneado en alcance (`20261111` + `20261114`): **156 pares**.
  - Pares deduplicados copiados a `data/raw/`: **87 pares** (`11` de `20261111` + `76` representantes únicos de `20261114`, filtrando `69` capturas redundantes de ráfaga).
  - Archivos escritos: **174** (`_orig.jpg` + `_annot.jpg`, `11,522,393` bytes).
  - Verificación bit a bit: **87/87** SHA-256 verificados y registrados en [`copy_receipt.json`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vigia_ml/data/raw/copy_receipt.json) + [`sandbox_raw_manifest_v1.json`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vigia_ml/data/processed/sandbox_raw_manifest_v1.json).

---

## 4. Esquema de Anotación Manual (Actividad B)

Definido en [`annotation_schema.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vigia_ml/src/dataset/annotation_schema.py), [`schema_v1.json`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vigia_ml/data/annotations/schema_v1.json) y [`annotations_v1_template.json`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vigia_ml/data/annotations/annotations_v1_template.json):

- **Taxonomía cerrada de clases:** `CAR`, `MOTORCYCLE`, `BUS`, `TRUCK`, `OTHER`, `IGNORE`.
- **Taxonomía cerrada de colores:** `WHITE`, `BLACK`, `GRAY`, `SILVER`, `RED`, `BLUE`, `GREEN`, `YELLOW`, `BROWN`, `ORANGE`, `OTHER`, `INDETERMINATE`.
- **Atributos por objeto:** `bbox_xyxy`, `vehicle_class`, `observed_color`, `visibility`, `occlusion`, `lighting_condition`, `blur_level`, `annotator_notes`, `annotator_id`, `reviewer_id`, `review_status`.
- **Aislamiento de YOLO:** `YoloAuxReference` prohíbe explícitamente `is_ground_truth=True` mediante validación en constructor.
- **Mecanismo de doble revisión:** `AnnotationDataset.compare_double_annotation()` compara anotadores distintos, marca `DISPUTED` ante desacuerdo en clase o color y registra un objeto `AnnotatorDisagreement`.
- **Estado actual de anotaciones:** `0` objetos auto-etiquetados; plantilla lista (`PENDING_HUMAN_REVIEW` / vacía) para iniciar anotación manual por el estudiante.

---

## 5. Prototipo Baseline A y Diseño Técnico Baseline B (Actividad C)

### 5.1 Baseline A — Visión Artificial Clásica ([`baseline_classic.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vigia_ml/src/color_analysis/baseline_classic.py))
- Convierte BGR a **HSV** y **CIELAB**, aplica recorte interior (`12%`) y peso espacial elíptico centrado, filtra sombras profundas (`V < 32` y `L* < 18`) y brillos especulares (`V > 246` y `S < 26`), evalúa máscaras cromáticas/acromáticas junto con cromaticidad CIELAB y devuelve:
  - `predicted_color` (incluyendo **`INDETERMINATE`** si área `< 400 px`, `mean_V < 24`, señal válida `< 18%`, glare `> 75%` o ambigüedad entre top-1/top-2),
  - `category_scores` normalizados,
  - `quality_indicator` y `hsv_histogram_summary`.
- **Smoke test ejecutado ([`baseline_a_smoke_report.json`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vigia_ml/reports/baseline_a_smoke_report.json)):**
  - Evaluó los **87** fotogramas en `data/raw/` usando únicamente la ROI general de cámara (`has_human_ground_truth = false`, sin bboxes vehiculares estrechos):
  - Distribución observada: `{"ORANGE": 62, "BLUE": 8, "INDETERMINATE": 8, "BROWN": 5, "BLACK": 3, "RED": 1}` (`indeterminate_rate = 0.092`; flags de calidad: `OK: 79`, `AMBIGUOUS_CHROMA: 5`, `INSUFFICIENT_ILLUMINATION_OR_SIGNAL: 3`).
  - **Diagnóstico empírico clave:** Al aplicar ROI completa de cámara en lugar de bounding boxes vehiculares ajustados, el fondo cálido del escritorio domina la región evaluada (`ORANGE: 62`). Esto demuestra cuantitativamente por qué el recorte anotado manualmente (Actividad B) es indispensable antes de medir exactitud cromática.

### 5.2 Baseline B — Diseño Técnico ML Clásico ([`color_features.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vigia_ml/src/models/color_features.py), [`baseline_ml.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vigia_ml/src/models/baseline_ml.py))
- Vector determinista de **75 características** (histogramas L1 normalizados `16` Hue + `8` S + `8` V + `8×3` CIELAB, más `mean, std, p10, p50, p90` por los 6 canales y 3 ratios de calidad tras enmascarar sombras/reflejos).
- Pipelines encapsulados `StandardScaler` + `SVC(kernel='rbf', probability=True)` o `RandomForestClassifier`, con rechazo `INDETERMINATE` cuando `max(proba) < 0.50`.
- **Bloqueos de seguridad (`DomainSafetyError`):** Impide entrenar sin Ground Truth verificado (`ground_truth_verified=True`, salvo bandera explícita de prueba unitaria) e impide mezclar `REAL_FULL_SCALE` con `SCALE_MODEL_LAB` o `SCREEN_RECAPTURE`. No se ejecutó entrenamiento definitivo en esta fase.

---

## 6. Metodología de Evaluación, Documentación Académica y Pruebas (Actividades D y E)

- **Control de fugas (`anti-leakage`):** [`splits.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vigia_ml/src/evaluation/splits.py) implementa `GroupKFold` por `session_id` + `physical_object_id` y `assert_no_group_leakage()` verifica intersección vacía en `sha256`, `duplicate_group`, `session_id` y objeto físico.
- **Métricas ([`metrics.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vigia_ml/src/evaluation/metrics.py)):** `accuracy`, `precision_macro`, `recall_macro`, `f1_macro`, métricas por clase, matriz de confusión, `indeterminate_rate`, desglose `by_lighting_condition` y bandera `real_world_representative` (`False` por defecto mientras no sea `100% REAL_FULL_SCALE` con GT humano).
- **Documentación y reproducibilidad académica:**
  - [`README.md`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vigia_ml/README.md) y [`requirements.txt`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vigia_ml/requirements.txt).
  - [`METODOLOGIA_EVALUACION_ML.md`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vigia_ml/reports/METODOLOGIA_EVALUACION_ML.md).
  - [`GUIA_ACTIVIDADES_ESTUDIANTE_IA.md`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vigia_ml/reports/GUIA_ACTIVIDADES_ESTUDIANTE_IA.md) (incluye explicación detallada de los **12 fundamentos conceptuales** y plan paso a paso).
  - [`01_exploracion_y_color_sandbox.ipynb`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vigia_ml/notebooks/01_exploracion_y_color_sandbox.ipynb) (portable, **cero rutas absolutas**).
- **Pruebas unitarias ejecutadas:** `python -m unittest discover -s tests -v` $\to$ **9/9 pruebas `OK` en 0.206s** (validación de inventario/copia SHA-256, esquema de anotación y desacuerdos, Baseline A colores + `INDETERMINATE`, Baseline B extracción/guardas, `GroupKFold` y métricas).

---

## 7. Cumplimiento de Criterios de Aceptación y Próxima Fase

| Criterio | Estado | Evidencia |
|---|---|---|
| 1. Sandbox independiente | Cumplido | [`experiments/vigia_ml/`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vigia_ml) aislado de módulos productivos |
| 2. Evidencias originales protegidas | Cumplido | `source_untouched: true`; sin cambios en `evidencias_vigia/` |
| 3. Inventario reproducible | Cumplido | [`inventory.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vigia_ml/src/dataset/inventory.py) $\to$ `604` registros en `manifest_v1.*` |
| 4. Trazabilidad SHA-256 | Cumplido | [`copy_receipt.json`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vigia_ml/data/raw/copy_receipt.json) (`87/87` verificados) |
| 5. Esquema de anotación documentado | Cumplido | [`annotation_schema.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vigia_ml/src/dataset/annotation_schema.py) + [`schema_v1.json`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vigia_ml/data/annotations/schema_v1.json) |
| 6. Baseline A funcional en pruebas | Cumplido | Pruebas sintéticas OK + smoke test en `87` imágenes sandbox |
| 7. Diseño reproducible Baseline B | Cumplido | [`color_features.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vigia_ml/src/models/color_features.py) + [`baseline_ml.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vigia_ml/src/models/baseline_ml.py) |
| 8. Métricas y particiones definidas | Cumplido | [`splits.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vigia_ml/src/evaluation/splits.py) + [`metrics.py`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vigia_ml/src/evaluation/metrics.py) |
| 9. Pruebas unitarias | Cumplido | `9/9` unit tests pasando tras la edición final |
| 10. Guía clara del estudiante | Cumplido | [`GUIA_ACTIVIDADES_ESTUDIANTE_IA.md`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/experiments/vigia_ml/reports/GUIA_ACTIVIDADES_ESTUDIANTE_IA.md) + notebook |

**Declaración explícita de alcance:** El reconocimiento de color **NO está terminado** ni existe **ningún modelo entrenado o validado para producción**.  
**Próxima fase recomendada (`VIGIA-ML-03`):** Ejecución de anotación manual humana por el estudiante sobre `data/raw/` (generando recortes vehiculares reales y revisión cruzada) + captura física `1:1` de [`VIGIA-VISION-03B.1_PROTOCOLO_CAPTURA.md`](file:///C:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/Docs/fase_vision/VIGIA-VISION-03B.1_PROTOCOLO_CAPTURA.md) por parte de Ingeniería VIGÍA para habilitar comparativas válidas entre Baseline A y Baseline B.
