# 03.2 — Requerimientos No Funcionales

**Proyecto:** VIGIA Vision Systems  
**Área:** Gestión de Proyectos de Software / Ingeniería de Requisitos  
**Responsable del entregable:** Yair  
**Puesto / Rol del responsable:** Ingeniería de Software e Ingeniería de Diseño Eléctrico  
**Versión:** 1.3  
**Fecha:** 21 de octubre de 2026

---

## 1. Introducción

Los requerimientos no funcionales de VIGIA Vision Systems establecen las condiciones de calidad, seguridad, integridad, mantenibilidad y operación que el sistema cumple durante su funcionamiento.

Estos requisitos complementan los requerimientos funcionales y aseguran que las funciones de supervisión de accesos vehiculares, registro de eventos, consulta de información y generación de alertas se proporcionen bajo condiciones adecuadas para el alcance de la primera versión del proyecto.

Los requisitos se han definido procurando que puedan verificarse mediante pruebas, inspecciones o revisiones técnicas, de acuerdo con las características y los componentes efectivamente implementados.

---

## 2. Catálogo de Requerimientos No Funcionales (RNF)

| ID | Categoría | Nombre | Requerimiento no funcional |
| :---: | :--- | :--- | :--- |
| **RNF-01** | Seguridad | Autenticación de Usuarios | El sistema restringe el acceso a las funciones administrativas mediante un módulo de inicio de sesión obligatorio que valida las credenciales (usuario y contraseña) contra la base de datos local. |
| **RNF-02** | Seguridad | Autorización por Roles (RBAC) | El software aplica un control de acceso basado en roles (RBAC), validando los permisos asignados para limitar las pantallas operativas según el perfil: Administrador (gestión total) o Guardia de Seguridad (solo visualización de alertas y video). |
| **RNF-03** | Seguridad | Hashing de Contraseñas | El sistema protege las contraseñas de los usuarios en la base de datos aplicando el algoritmo de hashing criptográfico SHA-256, impidiendo el almacenamiento de texto plano para resistir ataques de fuerza bruta. |
| **RNF-04** | Seguridad | Protección de Datos en Reposo | El software cifra la información sensible almacenada (números de placa e imágenes de evidencia) mediante el estándar de cifrado simétrico AES-256 directamente en las tablas del motor de la base de datos. |
| **RNF-05** | Seguridad | Comunicaciones Cifradas | La cámara de vigilancia transmite el flujo de video y metadatos hacia el servidor local mediante el protocolo seguro RTSP con autenticación integrada, protegiendo el canal contra intercepciones externas. |
| **RNF-06** | Seguridad | Restricción de Registros de Supervisión | El sistema deniega el acceso a las bitácoras de auditoría forense e historial vehicular a cualquier usuario que no cuente con el rol verificado de Administrador. |
| **RNF-07** | Integridad | Consistencia de Datos | La base de datos mantiene la integridad de la información aplicando restricciones estructurales (FOREIGN KEY y NOT NULL), impidiendo que se almacenen placas con caracteres que no sean alfanuméricos. |
| **RNF-08** | Mantenibilidad | Registro de Bitácora de Errores | El software registra las fallas técnicas automáticamente en un archivo de texto plano `.log` local bajo el formato estandarizado `[Fecha][Hora][Componente][Código]`, aislando cualquier contraseña o dato personal. |
| **RNF-09** | Mantenibilidad | Arquitectura Modular | La arquitectura del código organiza el sistema en módulos independientes (captura, motor OCR y visualización de interfaz) mediante el uso de Git, reduciendo las dependencias innecesarias entre componentes. |
| **RNF-10** | Recuperabilidad | Respaldo y Restauración | El script automatizado ejecuta una copia de seguridad completa de la base de datos diariamente a las 00:00 horas en una unidad de almacenamiento externa, permitiendo la restauración del sistema mediante un procedimiento técnico documentado. |
| **RNF-11** | Usabilidad | Consistencia de la Interfaz (UX/UI) | La interfaz gráfica despliega los estados del sistema utilizando el manual de estilo del proyecto, diferenciando los accesos ordinarios en color gris y las alertas críticas de vehículos no autorizados en naranja/rojo, cumpliendo la relación de contraste 4.5:1 de la norma WCAG. |
| **RNF-12** | Privacidad | Limitación de Datos Personales | El sistema limita la recolección de metadatos estrictamente a los campos autorizados (placa, hora, fecha, marca, color y fotografía), eliminando de forma automatizada las imágenes de evidencia que superen los 30 días de antigüedad en el almacenamiento local. |
| **RNF-13** | Rendimiento | Tiempos de Respuesta | El motor OCR procesa los cuadros de video y arroja el resultado del reconocimiento en pantalla en un tiempo menor a 150 milisegundos por vehículo, manteniendo una disponibilidad de operación continua 24/7. |

---

## 3. Tecnologías y criterios técnicos de referencia

Las siguientes tecnologías y prácticas se utilizan para implementar y verificar los requisitos no funcionales, de acuerdo con las decisiones técnicas aprobadas y la arquitectura de VIGIA.

- **RBAC (Role-Based Access Control):** modelo de autorización que asigna permisos según los roles definidos (Administrador y Guardia de Seguridad) aplicando el principio de mínimo privilegio.
- **SHA-256:** algoritmo de hashing criptográfico para la protección de contraseñas en la base de datos local. Su configuración considera los recursos disponibles en el entorno de despliegue.
- **AES-256:** algoritmo de cifrado simétrico utilizado para proteger información sensible almacenada (placas e imágenes). Requiere una gestión adecuada de claves y selección correcta del modo de cifrado.
- **RTSP con autenticación:** protocolo para la transmisión segura del flujo de video entre la cámara de vigilancia y el servidor local, con autenticación integrada en el canal.
- **Validaciones y restricciones de integridad en la base de datos:** mecanismos como claves primarias, claves foráneas (FOREIGN KEY), restricciones NOT NULL y reglas de validación alfanumérica que mantienen la consistencia de los registros.
- **Registro de eventos técnicos (logging):** archivos `.log` locales con formato `[Fecha][Hora][Componente][Código]`, con acceso restringido y sin exposición de datos sensibles.
- **Respaldo y restauración automatizada:** script programado a las 00:00 horas para generar copias completas de la base de datos en unidad de almacenamiento externa, con procedimiento documentado de restauración.
- **Diseño modular con Git:** organización del software en módulos independientes (captura, OCR e interfaz) con control de versiones en Git, facilitando el mantenimiento y la evolución del sistema.
- **Motor OCR:** componente de reconocimiento óptico de caracteres integrado al procesamiento de video, con objetivo de respuesta menor a 150 ms por vehículo.
- **WCAG 2.1 — Contraste 4.5:1:** estándar de accesibilidad aplicado al diseño de la interfaz gráfica para garantizar legibilidad en condiciones de operación real.

---

## 4. Verificación y cumplimiento

El cumplimiento de los requerimientos no funcionales se comprueba mediante pruebas funcionales y no funcionales, inspecciones de configuración, revisiones del código y verificaciones de la infraestructura, según corresponda a cada requisito.

Las evidencias obtenidas distinguen entre los requisitos implementados y verificados, los que presenten limitaciones y los que permanezcan pendientes de implementación.

Los parámetros cuantitativos de rendimiento (≤ 150 ms por reconocimiento OCR), disponibilidad (24/7) y conservación de respaldos (retención de 30 días de imágenes) se establecen de acuerdo con las capacidades del hardware, la arquitectura desplegada y el alcance aprobado de la versión 1.

Los mecanismos de seguridad y protección de datos se evalúan considerando los componentes efectivamente utilizados y los riesgos asociados a la operación prevista de VIGIA.

---

## 5. Consideraciones de alcance

Los requerimientos no funcionales describen las condiciones de calidad y operación de la primera versión de VIGIA Vision Systems. Su inclusión en este documento no implica que una característica esté implementada o validada; su cumplimiento se respalda mediante evidencias técnicas.

Las tecnologías mencionadas constituyen referencias de implementación y no sustituyen la necesidad de verificar que los mecanismos seleccionados satisfagan los requisitos correspondientes.

Las mejoras que requieran infraestructura adicional, servicios externos o capacidades no contempladas en el alcance aprobado se evalúan antes de incorporarse como compromisos del proyecto.
