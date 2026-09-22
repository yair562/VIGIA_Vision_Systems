# VIGIA Vision Systems

## 08 — Matriz de Gestión de Riesgos

**Estado:** Activo / Fase 0  
**Versión:** 1.1 (Alineación y Desacoplamiento Tecnológico)  
**Fuente de Verdad:** Gestión de Riesgos y Planes de Mitigación  
**Responsables de Gobernanza:** Ernesto (CIO / Circuitos) & Yair (Software / Eléctrico)  
**Propósito:** Identificar, evaluar, priorizar y establecer estrategias de mitigación para los riesgos técnicos, operacionales y de integración que puedan comprometer la entrega de VIGIA Vision Systems en el plazo fijado (16 de diciembre de 2026).

---

> **Nota Metodológica:**  
> Los valores de *Probabilidad*, *Impacto* y *Prioridad* consignados en esta matriz corresponden a la **evaluación inicial del Sprint 0 y están sujetos a validación y ajuste continuo** en cada sesión de Sprint Planning y Sprint Review. Las tecnologías mencionadas en las respuestas representan **opciones de implementación candidatas**, no decisiones arquitectónicas cerradas.

---

# 1. Escala de Evaluación y Criterios

Para garantizar una priorización objetiva, se utiliza la siguiente escala cualitativa:

* **Probabilidad:**
  * `Baja`: Poco probable que ocurra bajo condiciones estándar de laboratorio/banco de pruebas.
  * `Media`: Probabilidad moderada debido a variabilidad ambiental o dependencias técnicas.
  * `Alta`: Alta probabilidad si no se toman medidas preventivas tempranas.
* **Impacto:**
  * `Bajo`: Causa demoras menores sin afectar el flujo crítico del ciclo rector ni la fecha del Sprint.
  * `Medio`: Afecta el rendimiento de un módulo específico pero permite integración mediante *mocks*.
  * `Alto`: Compromete la funcionalidad de una capacidad completa en el entorno físico.
  * `Crítico`: Bloquea la integración de extremo a extremo o pone en riesgo la fecha límite inamovible (16 de diciembre).
* **Prioridad:**
  * Calculada mediante la combinación de Probabilidad e Impacto (`Crítica`, `Alta`, `Media`, `Baja`).

---

# 2. Matriz Consolidada de Riesgos del Proyecto

| ID | Riesgo | Causa Raíz | Evento No Deseado | Efecto en el Proyecto | Probabilidad* | Impacto* | Prioridad* | Estrategia de Respuesta | Mecanismo de Seguimiento | Responsable Técnico Principal |
| :-: | :--- | :--- | :--- | :--- | :---: | :---: | :---: | :--- | :--- | :--- |
| **R-01** | **Baja precisión de OCR/LPR en placas vehiculares** | Variabilidad de iluminación, reflejos en matrícula, ángulos de cámara o placas no estándar. | Falso rechazo, placa no leída o lectura con caracteres erróneos. | Apertura denegada a vehículos autorizados o necesidad de intervención manual permanente. | Media | Alto | **Alta** | **Mitigación:** Preprocesamiento de imagen (recorte ROI, binarización adaptativa), umbral de confianza mínimo y colector de casos dudosos (*Active Learning*). | Métricas de precisión/recall en dataset de pruebas semanal en `VIGIA_Vision`. | Estef (Analista) |
| **R-02** | **Fallos de comunicación o congelamiento de microcontrolador** | Ruido electromagnético por servomotores, desconexión del cable USB o saturación de buffer UART. | Pérdida de enlace serial entre `VIGIA_Core` y `VIGIA_IoT`. | Imposibilidad de accionar la barrera o leer sensores de verificación física; carril bloqueado. | Media | Crítico | **Crítica** | **Mitigación:** Implementar *Watchdog Timer* en microcontrolador, reconexión automática en caliente en driver Python y modo seguro (*Fail-Safe*). | Logs de telemetría serial y pruebas de desconexión en caliente en Sprint 2. | Ernesto (CIO / Circuitos) |
| **R-03** | **Retrasos de hardware físico que bloqueen el desarrollo de software** | Demoras en compra de componentes, rotura de servomotores o problemas de cableado en maqueta. | Desarrolladores de Core, API y Dashboard sin hardware disponible para probar. | Retraso en cadena en el cronograma de sprints. | Alta | Crítico | **Crítica** | **Prevención:** Regla estricta de no bloqueo: emulación obligatoria con *mocks* seriales (`mock_serial.py`) y videos pregrabados en `tests/`. | Verificación de suite de pruebas con mocks en cada Pull Request. | Natalia (UX/UI) + Yair (Software) |
| **R-04** | **Sobreingeniería y complejidad técnica innecesaria** | Tendencia a introducir microservicios, brokers de mensajería externos o bases distribuidas sin necesidad real. | Código sobrecomplejo, difícil de depurar y mantener por un equipo de 6 personas. | Retrasos críticos y desvío de los objetivos del caso de uso rector. | Media | Alto | **Alta** | **Control / Rechazo:** Aplicación obligatoria del *Filtro de las 6 Preguntas Tecnológicas* (`Docs/04`). | Revisión arquitectónica en PRs por el área de Software y Product Owner. | Yair (Software) + Vianey (PO) |
| **R-05** | **Incompatibilidad entre esquemas de API y Dashboard** | Modificaciones en payloads de datos de backend sin coordinación con frontend. | Fallos de renderizado en Dashboard, controles inoperativos o datos desalineados en visualización. | Retrabajo en etapas tardías de integración (Sprint 5). | Media | Medio | **Media** | **Mitigación:** Definición previa de contratos tipados de datos y esquemas de API en Sprint 1 antes de programar la UI. | Pruebas de contrato automatizadas entre `VIGIA_API` y `VIGIA_Dashboard`. | Yair (Software) + Natalia (UX/UI) |
| **R-06** | **Latencia excesiva en inferencia de visión computacional** | Ejecución de modelos de detección pesados en CPU sin aceleración gráfica o hardware edge limitado. | Tiempo de procesamiento por cuadro prolongado; retraso visible en detección de aproximación. | Experiencia de acceso lenta, acumulación de vehículos en carril de entrada. | Media | Alto | **Alta** | **Mitigación:** Evaluación de arquitecturas optimizadas para edge (candidatos: detectores ultraligeros, cuantización de modelos) y procesamiento asíncrono. | Benchmark formal de FPS y latencia en hardware objetivo durante Sprint 2. | Estef (Analista) + Yair (Software) |
| **R-07** | **Corrupción o pérdida de bitácora local por corte de energía abrupto** | Apagado inesperado del computador host sin cierre limpio de base de datos. | Pérdida del historial de eventos o inconsistencia en la base de datos de auditoría. | Pérdida de trazabilidad y evidencia fotográfica del evento. | Baja | Alto | **Media** | **Mitigación:** Configuración transaccional robusta en base de datos local (escrituras atómicas, modo seguro de bitácora) y respaldos periódicos. | Pruebas de corte de energía simulado y recuperación en Sprint 4. | Yair (Software) |
| **R-08** | **Inconsistencia de rutas o entornos locales no reproducibles** | Uso de rutas absolutas hardcodeadas o dependencias no fijadas en `requirements.txt`. | El software funciona en la máquina de un integrante pero falla en las de los demás. | Bloqueo en integración y revisiones de QA. | Media | Medio | **Media** | **Prevención:** Uso estricto de rutas relativas basadas en `Pathlib`, variables de entorno en `.env` y fijación de dependencias. | Auditoría continua de repositorios y linters en CI/DevOps. | Yair (Software) + Ernesto (CIO) |

*\*Nota: Valores cualitativos iniciales sujetos a validación en las revisiones de Sprint.*

---

# 3. Protocolo de Mitigación y Contingencia

### 3.1 Regla de Protección del Deadline (16 de Diciembre de 2026)
Conforme a lo estipulado en el Cronograma Maestro (`Docs/07`):

> **"Ante cualquier riesgo materializado que amenace la fecha límite, la respuesta estándar del proyecto es la REDUCCIÓN DE ALCANCE NO ESENCIAL, NUNCA el retraso de la fecha de entrega."**

### 3.2 Acciones de Contingencia por Capacidad:
1. **Si falla el OCR de alta precisión:** Se recurre al modo de simulación de placa o detección por lista simple de prueba mientras se refina el modelo, sin detener el avance de la barrera física.
2. **Si falla la barrera física:** Se valida la lógica con semáforo LED de dos estados (Verde/Rojo) y simulación por software del sensor de tope.
3. **Si se complica la comunicación bidireccional en tiempo real:** Se degrada temporalmente a sondeo HTTP periódico (*polling*) para mantener operativo el Dashboard.

---

# 4. Gobernanza y Monitoreo de Riesgos

* **Frecuencia de Revisión:** Cada sesión de **Sprint Review** y **Sprint Planning** quincenal.
* **Escalamiento:** Cualquier integrante que identifique un riesgo emergente con impacto potencial `Alto` o `Crítico` debe notificarlo de inmediato en las sesiones de equipo para su análisis y priorización.
