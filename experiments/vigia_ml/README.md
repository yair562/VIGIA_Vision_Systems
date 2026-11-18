# VIGIA-ML — Sandbox Experimental de Machine Learning y Atributos Vehiculares

Entorno de investigación **estrictamente aislado** del sistema productivo de **VIGÍA Vision Systems**.  
Su finalidad es permitir la curación reproducible de datos, la anotación manual con Ground Truth verificado por humanos y la experimentación de algoritmos de análisis cromático (Baseline A y Baseline B), **sin modificar ni acoplar nada a `VIGIA_Core`, `VIGIA_Vision`, `VIGIA_API`, `VIGIA_Dashboard`, `yolo11n.pt` o PostgreSQL**.

---

## Estructura del Sandbox

```text
experiments/vigia_ml/
├── README.md
├── requirements.txt
├── configs/
│   └── ml_experiment.yaml          # Parametros y taxonomias cerradas (rutas relativas)
├── data/
│   ├── raw/                        # Copias SHA-256 verificadas (subconjunto controlado)
│   ├── working/                    # Recortes o archivos intermedios de trabajo del estudiante
│   ├── annotations/                # Esquema JSON y plantilla de anotacion manual
│   └── processed/                  # Manifiestos CSV/JSON versionados (manifest_v1.*)
├── notebooks/
│   └── 01_exploracion_y_color_sandbox.ipynb
├── src/
│   ├── dataset/                    # inventory.py, controlled_copy.py, annotation_schema.py
│   ├── preprocessing/              # roi_crop.py
│   ├── color_analysis/             # baseline_classic.py (Baseline A: HSV + CIELAB)
│   ├── models/                     # color_features.py, baseline_ml.py (Baseline B: SVM/RF)
│   └── evaluation/                 # splits.py (GroupKFold), metrics.py, run_baseline_a_smoke.py
├── tests/                          # Pruebas unitarias reproducibles (unittest / pytest)
├── reports/                        # Metodologia, guia academica y reportes JSON
└── artifacts/                      # Salidas locales experimentales (figuras, modelos locales)
```

---

## Reglas de Aislamiento e Integridad

1. **Evidencias originales intactas:** Nunca editar, borrar o mover archivos dentro de `../../evidencias_vigia/`.
2. **Trazabilidad SHA-256:** Toda copia hacia `data/raw/` pasa por `src/dataset/controlled_copy.py` verificando hash SHA-256 origen vs. copia.
3. **Prohibido usar YOLO como Ground Truth:** Las predicciones de `yolo11n.pt` pueden cargarse únicamente en `yolo_aux_reference` (`is_ground_truth=false`) como ayuda visual, jamás como etiqueta verdadera.
4. **Control de fugas (`anti-leakage`):** Particionar siempre con `GroupKFold` por `session_id` / `duplicate_group` / `physical_object_id`.
5. **Separación de dominios:** No mezclar `SCALE_MODEL_LAB` ni `SCREEN_RECAPTURE` como si representaran vehículos reales `REAL_FULL_SCALE`.

---

## Instalación y Ejecución Rápida

Ejecute desde la raíz del sandbox (`experiments/vigia_ml/`):

```powershell
# 1. Opcional: crear entorno aislado o usar el Python cientifico existente
python -m pip install -r requirements.txt

# 2. Ejecutar inventario completo en solo lectura sobre evidencias historicas
python -m src.dataset.inventory

# 3. Ejecutar copia controlada deduplicada hacia data/raw/ con verificacion SHA-256
python -m src.dataset.controlled_copy --dates 20261111 20261114

# 4. Probar extractor Baseline A (HSV + CIELAB) sobre las muestras en data/raw/
python -m src.evaluation.run_baseline_a_smoke

# 5. Ejecutar todas las pruebas unitarias del sandbox
python -m unittest discover -s tests -v
```
