# Guía Académica y de Actividades — Estudiante de Inteligencia Artificial (VIGIA-ML-02)

Bienvenido al entorno experimental **VIGIA-ML**. Este documento sirve simultáneamente como **plan de trabajo paso a paso** y **referencia teórica** para sustentar académicamente el proyecto con rigor de ingeniería.

---

## Parte I — Fundamentos Conceptuales (Los 12 Pilares del Proyecto)

### 1. ¿Qué es Computer Vision?
Es la disciplina de la Inteligencia Artificial que permite a un sistema extraer información estructurada y comprensible (objetos, coordenadas, atributos, eventos) a partir de imágenes o secuencias de video representadas numéricamente como matrices de píxeles.

### 2. Diferencia entre detección de objetos y clasificación de atributos
- **Detección de objetos (ej. YOLO11n en VIGÍA):** Responde *«¿qué objeto hay y dónde está?»*, prediciendo una caja delimitadora `(x1, y1, x2, y2)` y una categoría estructural (`car`, `bus`, `truck`, `motorcycle`).
- **Clasificación de atributos (tu foco experimental):** Toma un recorte ya localizado del objeto y responde *«¿qué propiedades visuales tiene?»* (ej. color `RED`, `YELLOW`, `WHITE`, estado de visibilidad o nivel de oclusión).

### 3. ¿Qué es un dataset supervisado?
Es una colección estructurada de ejemplos de entrada $X$ (recortes de imagen) emparejados con etiquetas de salida esperadas $Y$ verificadas (clase o color real), junto con metadatos de procedencia y particiones limpias para entrenar y medir desempeño objetivamente.

### 4. ¿Qué es Ground Truth?
Es la referencia verdadera verificada por observación humana (y revisada por pares ante desacuerdos) contra la cual se evalúan los modelos. **Regla estricta en VIGÍA:** las predicciones automáticas de YOLO11n son únicamente una *referencia auxiliar*; nunca son Ground Truth hasta que un humano las corrige y aprueba.

### 5. Diferencias entre RGB/BGR, HSV y CIELAB
- **RGB / BGR:** Espacio aditivo ligado al hardware de sensores y pantallas (OpenCV lee matrices como `BGR`: Azul, Verde, Rojo). Su debilidad es que **mezcla color e intensidad luminosa**: cambiar el brillo modifica las tres coordenadas `B, G, R` simultáneamente.
- **HSV (Hue, Saturation, Value):** Separa el matiz cromático puro (`Hue`, ángulo `0–179` en OpenCV), la pureza/saturación (`Saturation`) y el brillo (`Value`). Facilita definir máscaras por rangos de color, aunque es inestable cuando `Saturation` o `Value` son muy bajos.
- **CIELAB ($L^*, a^*, b^*$):** Espacio diseñado para aproximar la percepción humana uniforme. Separa luminosidad perceptual ($L^*$) de los ejes oponentes verde–rojo ($a^*$) y azul–amarillo ($b^*$), permitiendo comparar diferencias cromáticas reales ($\Delta E$) y distinguir mejor colores oscuros o desaturados.

### 6. ¿Cómo se extraen características visuales?
En visión tradicional y ML clásico no pasamos píxeles crudos desordenados al clasificador, sino **descriptores resumidos invariantes**: histogramas normalizados de `H, S, V, L*, a*, b*`, percentiles (`p10, p50, p90`), medias/desviaciones tras enmascarar sombras y brillos especulares, y proporciones de píxeles válidos. (Ver `src/models/color_features.py`).

### 7. Diferencias entre algoritmos clásicos y Machine Learning
- **Algoritmo clásico (Baseline A):** Utiliza reglas matemáticas y umbrales explícitos diseñados por el ingeniero (máscaras HSV, filtros de reflejos, peso elíptico central). Es interpretable y funciona sin datos de entrenamiento, pero resulta rígido ante cambios imprevistos de iluminación.
- **Machine Learning clásico (Baseline B):** Aprende las fronteras de decisión automáticamente a partir de vectores de características extraídos de ejemplos etiquetados (ej. hiperplanos no lineales con `SVM RBF` o ensambles de árboles en `Random Forest`). Generaliza mejor si tiene datos variados, pero depende directamente de la calidad del dataset.

### 8. ¿Cómo se entrena y evalúa un clasificador?
1. Se limpian y etiquetan manualmente las muestras.
2. Se separan conjuntos estrictos de **entrenamiento**, **validación** (ajuste de hiperparámetros) y **prueba ciega** (evaluación final).
3. Se entrena un `Pipeline` (escalado + modelo) solo sobre *train*.
4. Se mide en *test* con métricas completas (`Accuracy`, `Macro-F1`, matriz de confusión, `% INDETERMINATE`, desglose por iluminación).

### 9. ¿Qué es *overfitting* (sobreajuste)?
Ocurre cuando un modelo memoriza detalles irrelevantes del conjunto de entrenamiento (el teclado del escritorio, el ángulo exacto de un juguete, el ruido de compresión de una ráfaga) logrando casi `100%` en entrenamiento, pero fallando severamente al ver un vehículo o iluminación nueva.

### 10. ¿Qué es *data leakage* (fuga de datos)?
Es la contaminación del conjunto de evaluación con información prácticamente idéntica al entrenamiento (por ejemplo, dividir aleatoriamente frames tomados cada 3 segundos del mismo vehículo inmóvil). En VIGÍA, el `47.3%` de transiciones de `CAM-SALIDA` tienen `MAD < 8`: un *split* aleatorio produce un *leakage* grave y métricas ilusoriamente altas.

### 11. ¿Cómo se realiza una validación por grupos?
Agrupando todas las muestras correlacionadas mediante un identificador compartido (`session_id`, `duplicate_group`, `physical_object_id`) y usando **`GroupKFold`**, de modo que **toda una sesión u objeto viaje completo al mismo lado del fold** (o todo en *train* o todo en *eval*, nunca dividido).

### 12. Limitaciones del experimento actual
- Los datos iniciales de `20261111` (`SCREEN_RECAPTURE`) y `20261114` (`SCALE_MODEL_LAB`) **no son vehículos reales en carril**.
- Existen apenas `3–4` objetos físicos distintos con fuerte desenfoque USB (`Laplaciana < 25`) y zonas oscuras (`Y < 30`).
- Por lo tanto, los resultados actuales validan **metodología, pipeline y comportamiento algorítmico**, nunca desempeño en producción real hasta incorporar capturas `1:1` de [`VIGIA-BENCH-REAL`](../../Docs/fase_vision/VIGIA-VISION-03B.1_PROTOCOLO_CAPTURA.md).

---

## Parte II — Ruta de Actividades del Estudiante (Orden Recomendado)

1. **Explorar el inventario:** Revisar `data/processed/manifest_v1.csv` y ejecutar `notebooks/01_exploracion_y_color_sandbox.ipynb` para inspeccionar resoluciones, nitidez (`sharpness_laplacian`), luminancia (`luminance_mean_y`) y clústeres de duplicados (`duplicate_group`).
2. **Realizar anotación humana piloto:** Tomar un lote de imágenes copiadas en `data/raw/` y documentar en un JSON siguiendo `data/annotations/schema_v1.json` (recuerda marcar `INDETERMINATE` si el color no se distingue con certeza visualmente).
3. **Ejecutar doble revisión y resolver desacuerdos:** Intercambiar un subconjunto (`>= 20%`) con un revisor usando `AnnotationDataset.compare_double_annotation()` para calcular concordancia y resolver etiquetas `DISPUTED`.
4. **Probar y calibrar Baseline A:** Analizar los casos donde `predict_color_classic()` acierta vs. donde falla o devuelve `INDETERMINATE` (sombras, luz verde ambiental, reflejos, fondo fuera de elipse).
5. **Preparar experimento comparativo Baseline B:** Una vez completado el manifiesto anotado humano (`ground_truth_verified=True`), extraer los vectores con `extract_color_feature_vector()` y comparar `SVM` vs. `Random Forest` vs. Baseline A bajo `GroupKFold`, documentando métricas estratificadas por iluminación sin mezclar dominios.
