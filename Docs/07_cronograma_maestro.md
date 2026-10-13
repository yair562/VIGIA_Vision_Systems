# VIGIA Vision Systems

## 07 — Cronograma Maestro de la V1

**Estado:** Activo  
**Versión:** 2.0 — Replanificación de prototipo escolar  
**Fecha de actualización:** 13 de octubre de 2026  
**Fecha objetivo de entrega:** 16 de diciembre de 2026  
**Metodología:** Scrum ligero con integración semanal  
**Fuente oficial:** Este documento

> Las fechas anteriores al 13 de octubre pertenecen a la planificación
> histórica. No se consideran tareas terminadas solamente porque su fecha
> original haya pasado. El estado real de cada actividad debe confirmarse con
> la evidencia indicada.

---

## 1. Propósito y alcance

Este cronograma convierte el alcance de VIGIA en un plan ejecutable para una
maqueta escolar. La prioridad no es construir una plataforma industrial, sino
demostrar de forma estable un flujo completo y repetible:

```text
Imagen o video de prueba
        |
        v
Detección de vehículo y placa, o simulación controlada
        |
        v
Validación de la observación
        |
        v
Consulta de vehículos y autorizaciones
        |
        v
Decisión permitido / denegado / revisión
        |
        v
Registro del evento
        |
        v
Visualización en dashboard
        |
        v
LED o servomotor opcional
```

El modo simulado es parte del alcance obligatorio. La demostración no puede
depender de que una cámara, un modelo OCR o un componente físico funcione
perfectamente el día de la entrega.

### Fuera del alcance obligatorio

No bloquean la V1: múltiples cámaras reales, entrenamiento de modelos propios,
MQTT, WebSockets, microservicios, alta disponibilidad, aplicación móvil,
firmware complejo, lazo cerrado industrial, sitio institucional completo y
despliegue edge.

---

## 2. Estado conocido y supuestos

### Confirmado en el repositorio

- Existe el prototipo de referencia `VR_Semaforo/` con código de visión y
  Arduino; permanece separado del nuevo sistema.
- La base de datos VIGIA tiene migraciones PostgreSQL V000–V003, runner,
  pruebas de integridad y documentación propia.
- La línea base de BD crea 15 tablas, incluyendo `vehiculo`, `deteccion` y
  `evento_acceso`.
- La documentación de roles identifica seis integrantes que cubren ocho
  funciones.

### No asumido como terminado

- No se da por implementado el backend nuevo.
- No se da por implementado el dashboard VIGIA.
- No se da por implementado un motor OCR integrado con la BD.
- No se da por disponible hardware específico para la demostración.
- No se asignan porcentajes de avance sin evidencia.

Si alguno de estos supuestos cambia, el Product Owner debe ajustar el alcance,
no ampliar silenciosamente la fecha ni la ruta crítica.

---

## 3. Roles y responsabilidad final

Se utilizan los roles oficiales documentados. Una persona puede cubrir más de
un rol, pero cada entregable tiene un único responsable final.

| Rol oficial | Responsable documentado | Responsabilidad en esta V1 |
|---|---|---|
| Product Owner (PO) | Vianey | Priorizar alcance, aceptar entregables y decidir qué se recorta. |
| Ingeniero de Software | Yair | Backend mínimo, integración con BD, contratos y ejecución técnica. |
| Ingeniero de Diseño Eléctrico | Yair | Requisitos eléctricos y alternativa segura de demostración física. |
| Analista | Estef | Casos de uso, datos de prueba, escenarios y validación de requisitos. |
| Ingeniero de Procesos | Josué | Flujo operativo, reglas de decisión y procedimiento de demostración. |
| UX/UI Designer | Natalia | Flujo de pantalla y dashboard mínimo demostrable. |
| CIO | Ernesto | Coordinación de recursos técnicos y apoyo a integración física. |
| Ingeniero de Diseño de Circuitos | Ernesto | LED, servo o circuito de maqueta, si los recursos están disponibles. |

La responsabilidad final de una tarea no se comparte entre varios roles. Los
demás roles aparecen como colaboradores en la matriz de cada fase.

---

## 4. Fases y fechas replanificadas

Las fases se ordenan por dependencia. Las actividades marcadas como paralelas
pueden avanzar simultáneamente después de cerrar su contrato mínimo.

### Fase 1 — Alcance, contratos y preparación

**Fechas:** 13–18 de octubre  
**Duración:** 1 semana  
**Responsable:** Product Owner  
**Colaboran:** Analista, Software, Procesos, UX/UI, CIO  
**Dependencias:** Ninguna; debe iniciar con el estado real del repositorio.

| Actividad | Entregable | Criterio de aceptación | Evidencia |
|---|---|---|---|
| Elegir el flujo principal | Alcance V1 de una página | Contiene entrada, decisión, registro y pantalla final | Aprobación del PO |
| Definir escenarios | Casos: permitido, denegado, ilegible y corrección | Cada escenario tiene entrada y resultado esperado | Tabla de casos |
| Congelar contrato mínimo | Payload de observación y decisión | Se puede usar con datos reales o fixtures | JSON de ejemplo validado |
| Definir criterios de demo | Lista de pruebas de aceptación | No depende de hardware ni OCR perfecto | Checklist aprobado |

**Hito H1 — 18 de octubre:** alcance reducido y contrato mínimo aprobados.

### Fase 2 — Datos, backend mínimo y reglas

**Fechas:** 19 de octubre–1 de noviembre  
**Duración:** 2 semanas  
**Responsable:** Ingeniero de Software  
**Colaboran:** Analista, Procesos, PO  
**Dependencia:** H1.

| Actividad | Entregable | Criterio de aceptación | Evidencia |
|---|---|---|---|
| Confirmar el esquema V000–V003 | Procedimiento de BD reproducible | Las migraciones y pruebas existentes se ejecutan en una BD aislada | Salida de `psql` y prueba |
| Crear acceso de datos | Consulta de vehículos y escritura de detecciones/accesos | Maneja coincidencia, ausencia y placa diferente | Pruebas automatizadas |
| Implementar reglas mínimas | Permitido, denegado y revisión | La decisión no sobrescribe la evidencia original | Casos de aceptación |
| Preparar datos de demo | Fixtures reproducibles | Incluye al menos una placa válida, una desconocida y una ilegible | Archivos de fixture |

**Paralelo permitido:** Analista prepara casos mientras Software prepara el
acceso a datos. Procesos valida las reglas antes de integrarlas.

**Hito H2 — 1 de noviembre:** una entrada controlada produce un evento
consultable y una decisión reproducible.

### Fase 3 — Visión artificial o simulación controlada

**Fechas:** 26 de octubre–8 de noviembre  
**Duración:** 2 semanas; puede iniciar en paralelo durante la segunda semana
de la Fase 2  
**Responsable:** Analista  
**Colaboran:** Ingeniero de Software, PO  
**Dependencia técnica:** contrato H1; integración con BD depende de H2.

| Actividad | Entregable | Criterio de aceptación | Evidencia |
|---|---|---|---|
| Preparar entrada | Imágenes o video corto de prueba | La ejecución es repetible en el equipo | Lote de fixtures |
| Probar lectura de placa | OCR experimental o adaptador simulado | Devuelve texto, `NULL` o baja confianza sin inventar datos | Resultados registrados |
| Generar observación | Payload compatible con `deteccion` | Conserva placa original y confianza | JSON y prueba |
| Definir fallback | Modo manual/simulado | El flujo continúa si falla OCR o cámara | Demostración en modo degradado |

**Regla:** no se entrena un modelo propio para esta V1. Si el OCR no es
estable, se utiliza simulación controlada y se documenta la limitación.

**Hito H3 — 8 de noviembre:** observaciones reproducibles disponibles por
visión o fixture.

### Fase 4 — Integración y dashboard mínimo

**Fechas:** 9–22 de noviembre  
**Duración:** 2 semanas  
**Responsable:** Ingeniero de Software  
**Colaboran:** UX/UI, Analista, Procesos, PO  
**Dependencias:** H2 y H3.

| Actividad | Entregable | Criterio de aceptación | Evidencia |
|---|---|---|---|
| Conectar observación con reglas | Flujo integrado | Una observación crea una decisión y un registro | Demo repetible |
| Construir pantalla mínima | Dashboard de un flujo | Muestra placa detectada, placa registrada, resultado y fecha | Capturas y ejecución |
| Mostrar evidencia | Imagen o referencia de fixture | La evidencia se relaciona con el evento | Caso de prueba |
| Integrar corrección manual | Corrección sin borrar lectura original | `placa_detectada` permanece disponible | Consulta de BD |

**Hito H4 — 22 de noviembre:** flujo completo funcionando sin hardware.

### Fase 5 — Hardware opcional y pruebas integrales

**Fechas:** 16–29 de noviembre  
**Duración:** 2 semanas  
**Responsable:** Ingeniero de Diseño de Circuitos  
**Colaboran:** CIO, Ingeniero de Diseño Eléctrico, Software, Procesos  
**Dependencia:** H4 para no bloquear la demo de software.

| Actividad | Entregable | Criterio de aceptación | Evidencia |
|---|---|---|---|
| Evaluar recursos físicos | Decisión de incluir o excluir hardware | La decisión considera tiempo, piezas y riesgo | Registro de decisión |
| Integrar LED o servo | Actuador simple, si procede | Permitido y denegado producen señales distintas | Video o prueba en banco |
| Definir modo degradado | Procedimiento sin hardware | La demo completa sigue funcionando | Checklist ejecutado |
| Ejecutar escenarios | Pruebas integrales | Coincidente, diferente, desconocida e ilegible pasan | Matriz de resultados |

El hardware es opcional para la aceptación de V1. No se incorporan MQTT,
firmware complejo ni sensores de lazo cerrado como dependencia de la entrega.

**Hito H5 — 29 de noviembre:** pruebas integrales y decisión de hardware
cerradas.

### Fase 6 — Estabilización y entrega

**Fechas:** 30 de noviembre–16 de diciembre  
**Duración:** 17 días  
**Responsable:** Product Owner  
**Colaboran:** Todo el equipo; Software coordina correcciones técnicas.
**Dependencia:** H5.

| Periodo | Actividad | Criterio de aceptación | Evidencia |
|---|---|---|---|
| 30 nov–6 dic | Corregir defectos críticos | No quedan fallos que impidan el flujo principal | Registro de defectos |
| 7–10 dic | Ensayo de instalación y demo | Otra persona puede repetir el procedimiento | Guía y video/acta |
| 11–13 dic | Feature freeze | Solo se aceptan correcciones críticas | Lista de cambios congelada |
| 14–15 dic | Empaquetado y documentación | Código, BD, fixtures y manual están disponibles | Paquete de entrega |
| 16 dic | Presentación | Se ejecutan los casos de aceptación | Acta o evidencia de demo |

**Hito H6 — 16 de diciembre:** prototipo integrado, reproducible y
demostrable.

---

## 5. Matriz resumida de responsabilidades

| Entregable | Responsable | Colaboradores | Dependencia |
|---|---|---|---|
| Alcance V1 y criterios | PO | Analista, Procesos | Ninguna |
| Casos y fixtures | Analista | Software, Procesos | Contrato H1 |
| Acceso a PostgreSQL y persistencia | Software | Analista | Alcance H1 |
| Reglas de decisión | Procesos | Software, PO | Casos H1 |
| Observación visual/simulada | Analista | Software | Contrato H1 |
| Dashboard mínimo | UX/UI | Software, Analista | Flujo H2/H3 |
| Hardware opcional | Diseño de Circuitos | CIO, Eléctrico | Flujo H4 |
| Pruebas de aceptación | PO | Todo el equipo | H4/H5 |
| Documentación y entrega | PO | Todo el equipo | H5 |

---

## 6. Ruta crítica y dependencias

```text
H1 Alcance y contrato
  -> H2 Datos y reglas
  -> H3 Observación reproducible
  -> H4 Integración y dashboard
  -> H5 Pruebas y modo degradado
  -> H6 Entrega
```

La fase de hardware no está en la ruta crítica porque el prototipo debe poder
demostrarse sin él. El OCR tampoco es una dependencia absoluta: el fixture
controlado es el respaldo aprobado para V1.

---

## 7. Clasificación del alcance

### Obligatorio para V1

- Flujo de imagen/fixture a observación.
- Registro de `deteccion` y `evento_acceso`.
- Consulta básica de vehículo y autorización.
- Decisión permitido, denegado o revisión.
- Conservación de la lectura original cuando haya corrección.
- Dashboard mínimo.
- Pruebas de escenarios y modo simulado.
- Procedimiento reproducible de instalación y demostración.

### Opcional

- OCR real estable.
- Cámara en vivo.
- LED o servomotor.
- Una pantalla adicional de alertas.
- Evidencia fotográfica local más completa.

### Futuro

- Múltiples cámaras.
- MQTT y WebSockets.
- Modelos propios y reentrenamiento.
- Microservicios y alta disponibilidad.
- Aplicación móvil.
- Sitio institucional completo.
- Lazo cerrado industrial y despliegue edge.

---

## 8. Riesgos y contingencias

| Riesgo | Impacto | Contingencia |
|---|---|---|
| OCR inestable | Alto | Fixtures y entrada manual controlada |
| Falta de hardware | Medio | Demo completa en modo simulado |
| Integración tardía | Alto | Demo vertical desde H2 y revisión semanal |
| Alcance creciente | Alto | PO congela V1 y pasa extras a futuro |
| Datos de prueba insuficientes | Medio | Lote mínimo de escenarios reproducibles |
| Confusión entre placa detectada y registrada | Alto | Mantener ambas semánticas en el contrato y la BD |
| Fallo de instalación | Medio | Ensayo desde una base aislada antes de entregar |

---

## 9. Criterios de cierre

La V1 se considera entregable cuando:

1. El flujo principal puede ejecutarse desde una imagen o fixture.
2. Se demuestran los casos permitido, denegado, ilegible y placa diferente.
3. La lectura original no se pierde al corregir la decisión.
4. El evento queda registrado y se visualiza en el dashboard.
5. La demostración funciona sin hardware y el hardware opcional no bloquea.
6. Las pruebas, fixtures, guía y documentación están disponibles.
7. El equipo puede explicar qué está implementado y qué quedó futuro.

No es criterio de cierre contar con entrenamiento propio, varias cámaras,
MQTT, WebSockets, microservicios ni automatización industrial.

---

## 10. Historial y decisiones abiertas

El documento archivado
[`Archive/07_Cronograma_Maestro_del_Proyecto.md`](./Archive/07_Cronograma_Maestro_del_Proyecto.md)
se conserva como referencia histórica. El archivo activo actual es la única
fuente oficial de fechas y compromisos.

Requieren confirmación humana:

- disponibilidad real de cámara, servo, LED y sensores;
- tecnología final del backend y dashboard;
- capacidad del equipo para implementar OCR real;
- fecha académica definitiva si difiere del 16 de diciembre;
- aceptación del modo simulado como criterio obligatorio de demostración.

Las decisiones abiertas no deben convertirse en compromisos de V1 hasta ser
aprobadas por el Product Owner.
