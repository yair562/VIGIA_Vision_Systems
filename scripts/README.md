# Scripts y Utilidades Auxiliares — VIGIA Vision Systems

**Herramientas Operativas, Mantenimiento y Automatización para Desarrolladores**

---

## 1. Responsabilidad del Directorio

El directorio `scripts/` alberga utilidades ejecutables fuera del flujo principal de la aplicación, destinadas a facilitar el trabajo diario del equipo de desarrollo, la verificación del entorno, tareas de mantenimiento y automatizaciones operativas.

Ninguna lógica central del sistema ni dependencia en tiempo de ejecución de producción debe residir en este directorio.

---

## 2. Tipología de Scripts Previstos

Durante las fases avanzadas del proyecto, se incorporarán herramientas como:

* **Verificación de Entorno:** Comprobación de versiones de Python, soporte de aceleración por GPU (CUDA/cuDNN/TensorRT), drivers de video y disponibilidad de puertos seriales.
* **Simuladores de Pruebas:** Emuladores interactivos por línea de comandos para inyectar tráfico sintético o enviar comandos de prueba al firmware de Arduino.
* **Descarga y Preparación de Modelos:** Scripts para descargar pesos preentrenados y convertirlos a formatos optimizados (ONNX, TensorRT, OpenVINO).
* **Calibración y Utilidades:** Herramientas para calcular matrices de calibración de perspectiva de cámaras y definición gráfica de polígonos de zonas de conteo.
* **Mantenimiento y Limpieza:** Scripts para depuración de logs temporales y optimización de bases de datos locales.

---

## 3. Estado Actual

> **IMPORTANTE:**  
> En esta etapa (**Fase 0**), no se agregan scripts innecesarios o prematuros.  
> Los scripts se desarrollarán de manera justificada conforme surjan necesidades operativas específicas.
