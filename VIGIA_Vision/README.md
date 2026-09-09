# VIGIA_Vision

**Subsistema de Percepción e Interpretación Visual: Detección y Lectura de Placas**

---

## 1. Responsabilidad del Módulo

`VIGIA_Vision` representa los **ojos y la capacidad de interpretación visual** de **VIGIA Vision Systems**:
$$\mathbf{OBSERVAR} \longrightarrow \mathbf{INTERPRETAR} \longrightarrow \text{Decidir} \longrightarrow \text{Actuar} \longrightarrow \text{Verificar} \longrightarrow \text{Registrar} \longrightarrow \mathbf{MEJORAR}$$

Su misión es capturar imágenes del entorno físico y transformarlas en información semántica con significado para el sistema:
* **Detectar vehículos:** Identificar automóviles, camionetas, camiones o motocicletas que se aproximan al carril de acceso.
* **Reconocer placas vehiculares (LPR / OCR):** Localizar la placa de matrícula y extraer sus caracteres alfanuméricos junto con su nivel de confianza.
* **Reconocer situaciones visuales:** Identificar si hay vehículos detenidos, obstáculos o dirección contraria.
* **Retroalimentar la mejora:** Aislar cuadros de imagen donde la lectura fue dudosa o con baja confianza para enriquecer el dataset de reentrenamiento (*Active Learning*).

> **Delimitación:**  
> `VIGIA_Vision` **observa e interpreta**, pero jamás decide si un vehículo tiene autorización ni envía pulsos a servomotores o barreras.

---

## 2. Componentes Previstos (Fase 2 del Roadmap)

* **Video Capture (`Captura de Video`):** Fuentes de video desacopladas (cámaras web USB, streams RTSP, archivos de video para pruebas).
* **Image Preprocessing (`Preprocesamiento`):** Ajustes de brillo, contraste, corrección de perspectiva y recorte del área de matrícula (ROI).
* **Object Detection (`Detección de Vehículos`):** Modelos ligeros y eficientes de detección (familia YOLO o clasificadores livianos).
* **License Plate Recognition (`Reconocimiento de Placas - LPR`):** Segmentación y lectura óptica de caracteres de placas vehiculares.
* **Active Learning Exporter (`Recolector de Casos Dudosos`):** Utilidad simple para guardar imágenes no identificadas con certeza para su posterior análisis y mejora del modelo.

---

## 3. Estado Actual

> **IMPORTANTE:**  
> En esta etapa (**Fase 0**), este módulo permanece intencionalmente sin código de implementación.  
> Se desarrollará en la Fase 2 del Roadmap para dotar a VIGIA de la capacidad de observar e interpretar.
