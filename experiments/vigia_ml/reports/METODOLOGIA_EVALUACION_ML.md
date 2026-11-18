# Metodología Experimental y Diseño de Evaluación — VIGIA-ML-02

## 1. Propósito y Alcance
Este documento formaliza la metodología experimental para evaluar algoritmos de **reconocimiento automático de color vehicular** dentro del sandbox `experiments/vigia_ml/`, garantizando rigor estadístico, control de fugas de datos (*data leakage*) y trazabilidad de dominio.

> **Advertencia de validez externa:** Ninguna métrica obtenida sobre `SCALE_MODEL_LAB` (`20261114`) o `SCREEN_RECAPTURE` (`20261111`) representa el desempeño operacional de VIGÍA sobre vehículos reales `1:1`. La certificación en escenario real exige el dataset [`VIGIA-BENCH-REAL`](../../Docs/fase_vision/VIGIA-VISION-03B.1_PROTOCOLO_CAPTURA.md) con Ground Truth humano.

---

## 2. Comparativa Estructural: Baseline A vs. Baseline B

| Aspecto | Baseline A — Visión Artificial Clásica | Baseline B — Machine Learning Clásico |
|---|---|---|
| **Implementación** | `src/color_analysis/baseline_classic.py` | `src/models/color_features.py` + `src/models/baseline_ml.py` |
| **Espacios de color** | BGR $\to$ HSV + BGR $\to$ CIELAB | BGR $\to$ HSV + BGR $\to$ CIELAB |
| **Preprocesamiento** | Recorte interior (`inner_crop_margin=0.12`), pesado elíptico central, filtrado de sombras profundas (`V<32 & L<18`) y reflejos especulares (`V>246 & S<26`) | Mismo enmascaramiento de sombras/reflejos para extraer histogramas normalizados (`16` Hue + `8` S + `8` V + `8×3` LAB) + estadísticos (`mean, std, p10, p50, p90`) + 3 ratios de calidad (`75` dimensiones totales) |
| **Decisión** | Reglas deterministas por máscaras HSV, umbrales acromáticos `L*/S/V` y atenuación por cromaticidad CIELAB | Clasificadores supervisados (`SVC(kernel='rbf', probability=True)` y `RandomForestClassifier`) con `StandardScaler` y balanceo de clases |
| **Manejo de incertidumbre** | Emite `INDETERMINATE` si el área ROI `< 400 px`, `mean_V < 24`, `usable_ratio < 0.18`, `glare > 75%` o margen entre top-1/top-2 `< 0.04` | Emite `INDETERMINATE` cuando `max(predict_proba) < 0.50` |
| **Requisito de datos** | No requiere entrenamiento; calibrable con pocas muestras de validación | Requiere Ground Truth humano anotado, partición sin fugas y variedad suficiente de instancias por clase |

---

## 3. Protocolo de Particionado sin Fugas (`GroupKFold`)

Las cámaras de videovigilancia generan ráfagas correlacionadas (en `20261114/CAM-SALIDA`, el `47.3%` de transiciones consecutivas presentan `MAD < 8`). Un *split* aleatorio imagen por imagen incurre en **fuga temporal y de objeto**:

1. **Deduplicación previa:** Cada clúster (`duplicate_group` asignado por `MAD < 8.0` o distancia Hamming `dHash <= 6`) aporta como máximo **una muestra representativa** al conjunto de trabajo cuando se ejecuta `controlled_copy.py`.
2. **Agrupación compuesta:** `src/evaluation/splits.py` agrupa obligatoriamente por `session_id` (y `physical_object_id` cuando esté anotado) mediante `GroupKFold`.
3. **Aserción automática de cero fugas:** `assert_no_group_leakage()` bloquea cualquier partición que comparta `sha256`, `duplicate_group`, `session_id` o `physical_object_id` entre *train* y *eval*.
4. **Aislamiento de dominios:** `separate_domains()` y `DomainSafetyError` impiden mezclar muestras `SCALE_MODEL_LAB` / `SCREEN_RECAPTURE` con `REAL_FULL_SCALE` en una misma métrica global.

---

## 4. Métricas Obligatorias (`src/evaluation/metrics.py`)

Toda corrida comparativa entre Baseline A y Baseline B debe registrar:
- **Exactitud global (`accuracy`)** y métricas macro-promediadas (**`precision_macro`**, **`recall_macro`**, **`f1_macro`**) para no ocultar fallos en clases minoritarias.
- **Desglose por clase (`per_class`):** `precision`, `recall`, `f1` y `support` para cada color evaluado.
- **Matriz de confusión (`confusion_matrix`)** para diagnosticar confusiones sistemáticas (ej. `RED` vs `BROWN`, `WHITE` vs `SILVER`, `BLACK` vs `GRAY`).
- **Tasa de abstención (`indeterminate_rate`):** Porcentaje de casos rechazados como `INDETERMINATE` (clave para medir honestidad ante baja luz o reflejos).
- **Estratificación por iluminación (`by_lighting_condition`):** Desempeño separado en `NORMAL`, `LOW_LIGHT`, `GLARE`, `COLOR_CAST` y `BACKLIT`.
- **Bandera `real_world_representative`:** Solo toma valor `true` cuando el `100%` de los datos evaluados pertenecen a `REAL_FULL_SCALE` con `ground_truth_status == "HUMAN_VERIFIED"`.
