# 03 — Requerimientos Funcionales y No Funcionales

**Proyecto:** VIGIA Vision Systems  
**Producto:** VIGIA *(Caso Rector: Caseta Inteligente de Acceso Vehicular)*  
**Área:** Ingeniería de Requisitos y Gestión de Software  
**Responsable del Entregable:** Yair  
**Puesto / Rol del Responsable:** Ingenieros de Software + Ing. de Diseño Eléctrico  
**Versión:** 1.0  
**Fecha:** 21 de septiembre de 2026  

---

## 1. Alcance y Contexto del Sistema

VIGIA es una plataforma física e inteligente para el control autónomo de acceso vehicular, articulada bajo el ciclo cerrado:

$$\text{Observar} \longrightarrow \text{Interpretar} \longrightarrow \text{Decidir} \longrightarrow \text{Actuar} \longrightarrow \text{Verificar} \longrightarrow \text{Registrar} \longrightarrow \text{Mejorar}$$

---

## 2. Requerimientos Funcionales (RF)

| ID | Nombre del Requisito | Descripción Funcional | Módulo Responsable | Estado |
| :-: | :--- | :--- | :---: | :---: |
| **RF-01** | **Captura de Flujo de Video** | El sistema debe capturar video en tiempo real desde una cámara orientada al carril de acceso a una tasa configurable. | `VIGIA_Vision` | 🟢 DEFINIDO |
| **RF-02** | **Detección de Presencia Vehicular** | El sistema debe detectar automáticamente la presencia de un vehículo cuando entra en la zona de aproximación visual o activa un sensor físico. | `VIGIA_Vision` / `VIGIA_IoT` | 🟢 DEFINIDO |
| **RF-03** | **Localización y Reconocimiento de Placa (LPR)** | El sistema debe segmentar la placa de matrícula del vehículo y extraer su cadena de caracteres junto con un índice de confianza. | `VIGIA_Vision` | 🟢 DEFINIDO |
| **RF-04** | **Evaluación Determinista de Autorización** | El sistema debe contrastar la placa reconocida y el momento del acceso contra las políticas y listas de vehículos autorizados. | `VIGIA_Automation` | 🟢 DEFINIDO |
| **RF-05** | **Validación de Invariantes de Seguridad** | `VIGIA_Core` debe validar que no existan condiciones de riesgo físico (ej. vehículo en zona de trayectoria de barrera o paro de emergencia activo) antes de autorizar cualquier actuación mecánica. | `VIGIA_Core` | 🟢 DEFINIDO |
| **RF-06** | **Comando de Actuación Física (Apertura)** | El sistema debe enviar la orden de apertura a la barrera electromecánica y conmutar la señalización física a paso habilitado si el acceso es concedido. | `VIGIA_IoT` | 🟢 DEFINIDO |
| **RF-07** | **Verificación Sensorial de Apertura** | El sistema debe confirmar mediante sensores físicos de tope/posición que la barrera alcanzó la posición abierta antes de considerar completada la maniobra. | `VIGIA_IoT` / `VIGIA_Core` | 🟢 DEFINIDO |
| **RF-08** | **Detección y Verificación de Cruce Completo** | El sistema debe confirmar mediante sensores de despeje (fotoceldas/lazos) que el vehículo completó el cruce antes de ordenar el cierre de la barrera. | `VIGIA_IoT` / `VIGIA_Core` | 🟢 DEFINIDO |
| **RF-09** | **Comando de Cierre Seguro** | El sistema debe ordenar el descenso de la barrera y conmutar la señalización a estado cerrado/alto tras confirmar el despeje físico del carril. | `VIGIA_IoT` | 🟢 DEFINIDO |
| **RF-10** | **Registro Persistente de Auditoría y Trazabilidad** | El sistema debe registrar de forma persistente y estructurada en almacenamiento local la fecha, hora, placa leída, nivel de confianza, decisión tomada, ruta de evidencia fotográfica y confirmaciones sensoriales. | `VIGIA_Core` / Adaptador DB | 🟢 DEFINIDO |
| **RF-11** | **Monitoreo Visual en Dashboard** | El sistema debe presentar en tiempo real al operador el estado actual del carril (Libre / En Espera / Autorizado / Cruzando / Denegado), vista de cámara y eventos operativos. | `VIGIA_Dashboard` / `VIGIA_API` | 🟢 DEFINIDO |
| **RF-12** | **Apertura Manual Supervisada** | El operador de caseta debe poder accionar la apertura manual supervisada desde el Dashboard ante excepciones, registrando obligatoriamente el evento y usuario. | `VIGIA_Dashboard` / `VIGIA_Core` | 🟢 DEFINIDO |
| **RF-13** | **Exportación de Casos Dudosos (Active Learning)** | El sistema debe archivar automáticamente imágenes de detecciones con baja confianza de lectura para enriquecer datasets de calibración posterior. | `VIGIA_Vision` | 🟢 DEFINIDO |
| **RF-14** | **Gestión de Lista de Autorizados** | El sistema debe permitir registrar, actualizar y dar de baja placas autorizadas con sus rangos de horario permitidos. | `VIGIA_API` | `[PENDIENTE EN SPRINT 1]` |
| **RF-15** | **Alerta por Bloqueo o Anomalía Mecánica** | El sistema debe emitir una alerta sonora/visual si la barrera no responde dentro del tiempo límite previsto tras la orden de maniobra. | `VIGIA_Core` / `VIGIA_Dashboard` | `[PENDIENTE EN SPRINT 1]` |

---

## 3. Requerimientos No Funcionales (RNF)

| ID | Categoría | Requisito de Calidad | Métrica / Criterio Objetivo | Estado |
| :-: | :--- | :--- | :--- | :---: |
| **RNF-01** | **Rendimiento** | Tiempo de ciclo de decisión (desde detección de cuadro hasta emisión de comando). | $\le 1.5\text{ s}$ en hardware objetivo de borde. | `[VALOR OBJETIVO — BENCHMARK EN S2]` |
| **RNF-02** | **Confiabilidad** | Operación autónoma en el borde sin requerir conectividad a servicios cloud externos. | 100% de funciones operativas en entorno local. | 🟢 DEFINIDO |
| **RNF-03** | **Testeabilidad** | Los módulos de software deben poder probarse sin requerir microcontrolador ni cámara física. | Cobertura mediante emuladores seriales y fixtures de video en `tests/`. | 🟢 DEFINIDO |
| **RNF-04** | **Seguridad Física** | Prioridad incondicional de seguridad (*Fail-Safe*) sobre órdenes de automatización. | Bloqueo físico de descenso ante detección de obstáculos. | 🟢 DEFINIDO |
| **RNF-05** | **Modularidad** | Acoplamiento débil entre módulos periféricos mediante contratos mediadas por el Core. | Cero dependencias directas entre Visión e IoT. | 🟢 DEFINIDO |
| **RNF-06** | **Mantenibilidad** | Código modular en Python conforme a estándares de legibilidad y tipado (`Docs/04`). | Aprobación de suites de pruebas y guías de estilo. | 🟢 DEFINIDO |

---

## 4. Reglas de Negocio Operativas e Invariantes

### 4.1 Reglas de Negocio (`VIGIA_Automation`)
* **RN-01:** Autorización válida únicamente si la matrícula coincide con un registro activo y el acceso ocurre dentro de la franja horaria permitida.
* **RN-02:** Si la matrícula no existe o no tiene permiso horario, se deniega el acceso y se notifica al Dashboard.
* **RN-03:** Temporizador de cruce: tras apertura, si el vehículo no avanza dentro del tiempo límite, se activa advertencia previa al cierre preventivo.

### 4.2 Invariantes de Seguridad (`VIGIA_Core`)
* **INV-01 (Anti-Aplastamiento):** Nunca ordenar descenso de barrera si el sensor de despeje/fotocelda detecta presencia vehicular en la zona de paso.
* **INV-02 (Confirmación de Barrera Abierta):** No conmutar señal a paso habilitado hasta recibir confirmación física del sensor de final de carrera superior.
* **INV-03 (Comportamiento Fail-Safe):** Ante pérdida de comunicación serial con el hardware, el sistema pasa a estado restrictivo de seguridad.
