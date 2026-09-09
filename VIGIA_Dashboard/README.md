# VIGIA_Dashboard

**Interfaz de Supervisión Operativa, Monitoreo Visual y Analítica**

---

## 1. Responsabilidad del Módulo

`VIGIA_Dashboard` es el entorno de interfaz de usuario de **VIGIA Vision Systems**. Proporciona a los guardias, supervisores y operadores de caseta una consola visual centralizada para supervisar en tiempo real el acceso vehicular, visualizar flujos de video con placas detectadas, verificar el estado de la barrera y sensores, y ejecutar aperturas manuales ante contingencias.

Este módulo se comunica exclusivamente a través de las APIs y canales en tiempo real provistos por `VIGIA_API`, garantizando total desacoplamiento de la lógica de procesamiento interno.

---

## 2. Componentes Conceptuales Previstos

Cuando se aborde la Fase 7 del Roadmap, este módulo integrará:

* **System Monitoring (`Monitoreo General del Sistema`):** Tableros de control en vivo que reflejan el estado operativo global, indicadores de salud, uso de recursos y modo de funcionamiento actual.
* **Camera Views (`Vistas de Cámaras en Vivo`):** Reproductores de video optimizados con soporte para superposición visual de cajas delimitadoras (`bounding boxes`), IDs de tracking y líneas de conteo virtual.
* **Events (`Visor de Eventos`):** Flujo cronológico interactivo de eventos del sistema (detecciones, cambios de fase, activaciones de sensores).
* **Alerts (`Gestor de Alertas`):** Notificaciones visuales y auditivas ante anomalías (congestión excesiva, detección de vehículos de emergencia, fallas de comunicación con microcontrolador).
* **Device Status (`Estado de Dispositivos`):** Panel de diagnóstico con la telemetría individual de cada cámara, sensor y actuador conectado (latencia, estado de conexión, versión de firmware).
* **Analytics (`Paneles Analíticos`):** Gráficas de tendencias de aforo vehicular, tiempos promedio de espera, tasas de flujo por carril y comparativas temporales.
* **Configuration (`Panel de Configuración`):** Formularios para ajustar umbrales, calibrar zonas de interés y modificar parámetros operativos de manera intuitiva.
* **Reports (`Generación de Reportes`):** Exportación de reportes de tráfico, auditoría de eventos y métricas de desempeño del sistema.

---

## 3. Estado Actual

> **IMPORTANTE:**  
> En esta etapa (**Fase 0**), este módulo permanece intencionalmente sin código de implementación.  
> La implementación de la interfaz se llevará a cabo en la Fase 7, diseñada para consumir los servicios de `VIGIA_API`.
