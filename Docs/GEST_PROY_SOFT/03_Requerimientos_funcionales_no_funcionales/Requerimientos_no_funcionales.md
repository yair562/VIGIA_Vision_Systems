# 03.2 — Requerimientos No Funcionales

**Proyecto:** VIGIA Vision Systems  
**Área:** Gestión de Proyectos de Software / Ingeniería de Requisitos  
**Responsable del entregable:** Yair  
**Puesto / Rol del responsable:** Ingeniería de Software e Ingeniería de Diseño Eléctrico  
**Versión:** 1.2  
**Fecha:** 23 de septiembre de 2026

---

## 1. Introducción

Los requerimientos no funcionales de VIGIA Vision Systems establecen las condiciones de calidad, seguridad, integridad, mantenibilidad y operación que deberá cumplir el sistema durante su funcionamiento.

Estos requisitos complementan los requerimientos funcionales y buscan asegurar que las funciones de supervisión de accesos vehiculares, registro de eventos, consulta de información y generación de alertas se proporcionen bajo condiciones adecuadas para el alcance de la primera versión del proyecto.

Los requisitos se han definido procurando que puedan verificarse mediante pruebas, inspecciones o revisiones técnicas, de acuerdo con las características y los componentes efectivamente implementados.

## 2. Catálogo de Requerimientos No Funcionales (RNF)

| ID | Categoría | Requerimiento no funcional |
| :---: | :--- | :--- |
| **RNF-01** | Seguridad | El sistema deberá proteger el acceso a las funciones restringidas mediante mecanismos de autenticación que permitan validar la identidad de los usuarios. |
| **RNF-02** | Seguridad | El sistema deberá aplicar controles de autorización basados en roles para limitar las operaciones disponibles a cada usuario según los permisos asignados. |
| **RNF-03** | Seguridad | El sistema no deberá almacenar contraseñas en texto plano; deberá protegerlas mediante un mecanismo de hashing de contraseñas adecuado para resistir ataques de recuperación por fuerza bruta. |
| **RNF-04** | Seguridad | El sistema deberá proteger la información sensible almacenada contra accesos no autorizados mediante mecanismos de protección de datos en reposo. |
| **RNF-05** | Seguridad | Las comunicaciones que transmitan información protegida a través de redes deberán utilizar canales cifrados y mecanismos de autenticación del servidor adecuados al entorno de despliegue. |
| **RNF-06** | Seguridad | El sistema deberá impedir que los usuarios accedan a información u operaciones para las que no tengan permisos, incluyendo los registros de vehículos y eventos de supervisión. |
| **RNF-07** | Integridad | El sistema deberá mantener la integridad y consistencia de los datos mediante validaciones y restricciones que impidan almacenar información que incumpla las reglas definidas para cada registro. |
| **RNF-08** | Mantenibilidad | El sistema deberá registrar los errores técnicos y fallos operativos relevantes con información suficiente para facilitar su diagnóstico y mantenimiento, sin exponer contraseñas ni otros datos sensibles innecesarios. |
| **RNF-09** | Mantenibilidad | La estructura del software deberá permitir mantener y modificar sus componentes de forma localizada, reduciendo las dependencias innecesarias entre módulos. |
| **RNF-10** | Recuperabilidad | El sistema deberá disponer de un procedimiento de respaldo y restauración que permita recuperar la información almacenada ante una pérdida de datos, de acuerdo con las políticas de respaldo definidas para el proyecto. |
| **RNF-11** | Usabilidad | La interfaz deberá presentar la información y los estados del sistema de manera consistente, legible y comprensible para el personal autorizado, diferenciando los eventos ordinarios de aquellos que requieran atención. |
| **RNF-12** | Privacidad | El sistema deberá limitar la recopilación, el almacenamiento y la exposición de datos personales a aquellos necesarios para las funciones autorizadas y contempladas en el alcance del proyecto. |
| **RNF-13** | Rendimiento | El sistema deberá proporcionar tiempos de respuesta adecuados para las operaciones de consulta y administración bajo las condiciones de operación y la carga de trabajo definidas para la versión 1. |
| **RNF-14** | Diagnóstico | El sistema deberá permitir identificar los fallos que afecten la disponibilidad de sus componentes principales mediante mecanismos de registro o diagnóstico apropiados a la arquitectura implementada. |
| **RNF-15** | Robustez | El sistema deberá mantener un comportamiento consistente ante entradas inválidas, errores de procesamiento o fallos recuperables, evitando que estas condiciones provoquen corrupción de datos o exposición de información protegida. |

## El sistema deberá alcanzar un nivel mínimo de precisión en el reconocimiento de matrículas, medido mediante un conjunto de imágenes de prueba representativo de las condiciones de operación previstas.

## 3. Tecnologías y criterios técnicos de referencia

Las siguientes tecnologías y prácticas podrán utilizarse para implementar y verificar los requisitos no funcionales, de acuerdo con las decisiones técnicas aprobadas y la arquitectura de VIGIA.

- **RBAC (Role-Based Access Control):** modelo de autorización que asigna permisos según los roles definidos para los usuarios y aplica el principio de mínimo privilegio.
- **Argon2id:** algoritmo de hashing de contraseñas diseñado para incrementar el costo de los ataques de adivinación de contraseñas. Su configuración deberá considerar los recursos disponibles en el entorno de despliegue.
- **AES-256:** algoritmo de cifrado simétrico que puede utilizarse para proteger información almacenada. Su aplicación requiere una gestión adecuada de claves y una selección correcta del modo de cifrado.
- **HTTPS y TLS:** mecanismos para proteger las comunicaciones entre componentes. La versión del protocolo y su configuración deberán ser compatibles con el entorno de despliegue y las necesidades de seguridad del proyecto.
- **Validaciones y restricciones de integridad en la base de datos:** mecanismos como claves primarias, claves foráneas, restricciones de unicidad, obligatoriedad de campos y reglas de validación que contribuyen a mantener la consistencia de los registros.
- **Registro de eventos técnicos (logging):** mecanismo para conservar información relevante sobre errores, excepciones y condiciones operativas, con acceso restringido y evitando registrar datos sensibles innecesarios.
- **Respaldos y restauración:** procedimientos para generar copias de seguridad y comprobar que la información pueda recuperarse de manera correcta.
- **Diseño modular:** organización del software en componentes con responsabilidades delimitadas, interfaces definidas y dependencias controladas, facilitando su mantenimiento y evolución.
- **Pruebas de rendimiento y robustez:** procedimientos para evaluar los tiempos de respuesta, el comportamiento ante entradas inválidas y la reacción del sistema frente a fallos bajo condiciones de prueba definidas.

---

## 4. Verificación y cumplimiento

El cumplimiento de los requerimientos no funcionales se comprobará mediante pruebas funcionales y no funcionales, inspecciones de configuración, revisiones del código y verificaciones de la infraestructura, según corresponda a cada requisito.

Las evidencias obtenidas deberán permitir distinguir entre los requisitos implementados y verificados, los que presenten limitaciones y los que permanezcan pendientes de implementación.

Los parámetros cuantitativos de rendimiento, disponibilidad, recuperación de información y conservación de respaldos deberán establecerse de acuerdo con las capacidades del hardware, la arquitectura desplegada y el alcance aprobado de la versión 1.

Los mecanismos de seguridad y protección de datos deberán evaluarse considerando los componentes efectivamente utilizados y los riesgos asociados a la operación prevista de VIGIA.

---

## 5. Consideraciones de alcance

Los requerimientos no funcionales describen las condiciones de calidad y operación esperadas para la primera versión de VIGIA Vision Systems. Su inclusión en este documento no implica que una característica esté implementada o validada; su cumplimiento deberá respaldarse mediante evidencias técnicas.

Las tecnologías mencionadas constituyen referencias de implementación y no sustituyen la necesidad de verificar que los mecanismos seleccionados satisfagan los requisitos correspondientes.

Las mejoras que requieran infraestructura adicional, servicios externos o capacidades no contempladas en el alcance aprobado deberán evaluarse antes de incorporarse como compromisos del proyecto.
