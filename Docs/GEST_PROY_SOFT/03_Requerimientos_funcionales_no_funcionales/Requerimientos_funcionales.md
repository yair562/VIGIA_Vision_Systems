# 03.1 — Requerimientos Funcionales

**Proyecto:** VIGIA Vision Systems  
**Área:** Gestión de Proyectos de Software / Ingeniería de Requisitos  
**Responsable del Entregable:** Yair  
**Puesto / Rol del Responsable:** Ingeniería de Software e Ingeniería de Diseño Eléctrico  
**Versión:** 1.2  
**Fecha:** 14 de octubre de 2026  

---

## 1. Catálogo de Requerimientos Funcionales (RF)

Los requerimientos funcionales de VIGIA Vision Systems establecen las funciones que el sistema deberá proporcionar para la supervisión de accesos vehiculares, el registro de eventos, la consulta de información y la identificación de situaciones que requieran atención del personal autorizado.

Su definición considera las necesidades identificadas en la encuesta de percepción y los objetivos funcionales contemplados para la primera versión del proyecto. Cada requisito describe un comportamiento esperado del sistema, procurando que sea claro, verificable y congruente con su alcance.

| ID | Requerimiento funcional |
| :---: | :--- |
| **RF-01** | El sistema deberá capturar imágenes del acceso vehicular mediante las cámaras configuradas para su operación. |
| **RF-02** | El sistema deberá analizar las imágenes capturadas para detectar vehículos presentes en el área supervisada. |
| **RF-03** | El sistema deberá identificar la matrícula de un vehículo detectado cuando la imagen capturada permita su lectura. |
| **RF-04** | El sistema deberá registrar los eventos de acceso vehicular detectados, incluyendo la fecha y hora correspondientes. |
| **RF-05** | El sistema deberá asociar la evidencia visual disponible con el evento de acceso vehicular correspondiente. |
| **RF-06** | El sistema deberá almacenar los registros de eventos y su evidencia visual asociada para su consulta posterior. |
| **RF-07** | El sistema deberá permitir registrar vehículos y sus datos de identificación, incluyendo la matrícula y el estado de autorización. |
| **RF-08** | El sistema deberá permitir consultar, actualizar y administrar los registros de vehículos almacenados. |
| **RF-09** | El sistema deberá comparar la matrícula identificada con los registros de vehículos almacenados cuando exista información suficiente para realizar la comparación. |
| **RF-10** | El sistema deberá determinar si un vehículo identificado coincide con un registro de autorización vigente, de acuerdo con la información almacenada. |
| **RF-11** | El sistema deberá identificar los eventos en los que no se encuentre una coincidencia con un registro de vehículo autorizado y diferenciarlos de aquellos en los que no sea posible identificar la matrícula. |
| **RF-12** | El sistema deberá permitir al personal autorizado consultar los eventos registrados y la información disponible de los vehículos relacionados. |
| **RF-13** | El sistema deberá permitir filtrar los registros de eventos mediante los criterios de consulta que se encuentren habilitados, incluyendo la fecha y la matrícula cuando estén disponibles. |
| **RF-14** | El sistema deberá generar una alerta visual cuando un evento cumpla las condiciones de alerta configuradas, incluyendo la detección de un vehículo sin autorización coincidente. |
| **RF-15** | El sistema deberá mostrar al personal autorizado la información disponible del evento que originó una alerta, incluyendo la matrícula identificada, la fecha y hora, y la evidencia visual asociada, cuando estos datos estén disponibles. |

---

## 2. Consideraciones sobre el alcance funcional

Los requerimientos anteriores describen las funciones previstas para la versión 1 de VIGIA Vision Systems. Su implementación estará sujeta al alcance aprobado del proyecto y a las capacidades verificadas durante el desarrollo y las pruebas del sistema.

La identificación de un vehículo sin coincidencia en los registros no constituye, por sí misma, una confirmación de actividad delictiva. Asimismo, cuando una matrícula no pueda leerse correctamente, el sistema deberá distinguir esa condición de la detección de un vehículo sin autorización registrada.

Los requerimientos relacionados con la captura de imágenes, el reconocimiento de matrículas, el almacenamiento de evidencia y la generación de alertas deberán verificarse considerando las condiciones de operación y las limitaciones de los componentes integrados.

Las funciones adicionales que no formen parte del alcance aprobado de la primera versión podrán evaluarse posteriormente, sin considerarse compromisos de implementación por el solo hecho de haber sido mencionadas en la encuesta.

---

## 3. Trazabilidad con la encuesta de percepción

La encuesta aplicada a 49–50 participantes no determina por sí sola todas las funciones del producto, pero proporciona una base para priorizar las necesidades que el sistema debe atender en su primera versión.

### 3.1 Supervisión e identificación de vehículos

El **49%** de los participantes señaló como preocupación principal la insuficiencia de vigilancia para detectar vehículos extraños o sospechosos.

Requisitos relacionados: **RF-01, RF-02, RF-03, RF-09, RF-10, RF-11**

### 3.2 Trazabilidad y consulta de accesos

El **36.7%** expresó preocupación por no contar con un registro confiable de las entradas y salidas. Además, el **46%** indicó que le resultaría útil consultar toda la información propuesta sobre los vehículos.

Requisitos relacionados: **RF-04, RF-05, RF-06, RF-12, RF-13**

### 3.3 Detección de vehículos sin autorización y alertas

El **64%** consideró muy importante recibir una alerta ante la detección de un vehículo no autorizado, y el **34%** adicional la consideró importante.

Requisitos relacionados: **RF-10, RF-11, RF-14, RF-15**

---

## 4. Definición de requerimiento funcional

Un **requerimiento funcional** es una declaración que especifica una función, servicio o comportamiento que un sistema debe proporcionar para satisfacer las necesidades de sus usuarios o los objetivos del negocio.

En VIGIA Vision Systems, los requerimientos funcionales establecen los comportamientos esperados para supervisar accesos vehiculares, registrar eventos, consultar información y generar alertas bajo las condiciones definidas para el sistema. Cada requisito describe **qué debe hacer el sistema**, no cómo se implementará técnicamente.