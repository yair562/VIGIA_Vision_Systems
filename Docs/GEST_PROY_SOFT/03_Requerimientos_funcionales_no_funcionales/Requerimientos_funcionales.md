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

|    ID     | Requerimiento funcional                                                                                                                                                                                                                                                                         |
| :-------: | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **RF-01** | El sistema deberá permitir la captura de imágenes del acceso vehicular mediante cámaras de dispositivos móviles, cámaras conectadas por USB y cámaras IP accesibles mediante una dirección de red.                                                                                              |
| **RF-02** | El sistema deberá permitir registrar y configurar las cámaras que se utilizarán para la supervisión del acceso vehicular, incluyendo el tipo de cámara, el área de detección y la dirección del acceso (entrada o salida).                                                                      |
| **RF-03** | El sistema deberá analizar las imágenes de las cámaras configuradas para detectar vehículos que se encuentren dentro del área de detección establecida para cada cámara, ignorandolos vehículos que permanezcan fuera de dicha área.                                                            |
| **RF-04** | El sistema deberá identificar y extraer los caracteres de la matrícula de los vehículos detectados cuando la imagen capturada permita su lectura.                                                                                                                                               |
| **RF-05** | El sistema deberá identificar las características visuales de los vehículos detectados, incluyendo su color y categoría (automóvil, motocicleta, camión u otra categoría contemplada), registrando los resultados como estimaciones cuando no sea posible obtener una identificación confiable. |

| **RF-06** | El sistema deberá registrar los eventos de entrada y salida vehicular confirmados, incluyendo la fecha, hora, dirección del acceso, evidencia visual y datos obtenidos durante el procesamiento, cuando estén disponibles. |
| **RF-07** | El sistema deberá permitir consultar la información del alumno mediante su matrícula institucional y verificar si cuenta con una motocicleta registrada y asociada a su registro. |
| **RF-08** | El sistema deberá almacenar los registros de eventos y su evidencia visual asociada para su consulta posterior. |
| **RF-09** | El sistema deberá permitir registrar al alumno mediante su matrícula institucional, asociar a su registro los datos del vehículo y la documentación requerida, incluyendo la licencia de conducir, la tarjeta de circulación y sus respectivas fechas de vencimiento. |
| **RF-10** |El sistema deberá permitir al oficial registrar la matrícula institucional del alumno desde la interfaz de la tablet y asociarla con la matrícula de su motocicleta para su identificación en accesos posteriores.|

**Administradores**

| **RF-11** | El sistema deberá permitir al personal autorizado consultar, actualizar y administrar los registros de vehículos almacenados. |
| **RF-12** | El sistema deberá comparar la matrícula reconocida con los registros de vehículos almacenados cuando exista información suficiente para realizar la comparación. |
| **RF-13** | El sistema deberá indicar si la matrícula reconocida tiene una coincidencia en los registros de vehículos almacenados. |
| **RF-14** | El sistema deberá indicar si la autorización del vehículo está vigente cuando los datos almacenados permitan confirmarlo. |
| **RF-15** | El sistema deberá diferenciar entre un vehículo cuya matrícula no sea reconocida o resulte ilegible y un vehículo cuya matrícula reconocida no tenga coincidencia en los registros. |
| **RF-16** | El sistema deberá permitir al personal autorizado consultar los eventos registrados y la información disponible de los vehículos relacionados. |
| **RF-17** | El sistema deberá permitir filtrar los registros de eventos por fecha y por matrícula cuando esta se encuentre disponible. |
| **RF-18** | El sistema deberá generar una alerta visual cuando un evento cumpla las condiciones de alerta configuradas, incluida la detección de un vehículo cuya autorización vigente no pueda confirmarse con la información disponible. |
| **RF-19** | El sistema deberá mostrar al personal autorizado los detalles y las evidencias disponibles del evento que originó una alerta, incluyendo la matrícula reconocida, la fecha y hora, y la evidencia visual asociada cuando estén disponibles. |

### 1.1 Estados funcionales de identificación y autorización

Para evitar interpretaciones equivalentes entre funciones distintas, el sistema deberá manejar y conservar la diferencia entre los siguientes estados:

1. **Vehículo detectado:** se identificó la presencia de un vehículo dentro del área de detección configurada.
2. **Matrícula reconocida:** se obtuvo información suficiente de la matrícula para intentar una comparación, sin que esto implique que la lectura sea necesariamente correcta.
3. **Matrícula no reconocida o ilegible:** no se obtuvo información suficiente de la matrícula para realizar una comparación.
4. **Matrícula reconocida sin coincidencia:** la matrícula reconocida no corresponde con un registro almacenado.
5. **Vehículo con coincidencia:** la matrícula reconocida corresponde con un registro almacenado.
6. **Autorización vigente confirmada:** los datos almacenados permiten confirmar que la autorización está vigente.

La falta de coincidencia no deberá presentarse como evidencia de una actividad delictiva. La confirmación de autorización vigente dependerá de que los registros contengan datos suficientes para determinarla; cualquier regla de vigencia no documentada queda pendiente de definición.

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

El documento reporta que el **49%** de los participantes señaló como preocupación principal la insuficiencia de vigilancia para detectar vehículos extraños o sospechosos. El porcentaje, el tamaño exacto de la muestra y su correspondencia con una pregunta concreta quedan **pendientes de validación documental** mediante el instrumento y los resultados originales de la encuesta.

Requisitos relacionados: **RF-01, RF-02, RF-03, RF-11, RF-12, RF-13, RF-14, RF-15**

### 3.2 Trazabilidad y consulta de accesos

El documento reporta que el **36.7%** expresó preocupación por no contar con un registro confiable de las entradas y salidas y que el **46%** indicó que le resultaría útil consultar la información propuesta sobre los vehículos. Estos porcentajes, el tamaño exacto de la muestra y su correspondencia con preguntas concretas quedan **pendientes de validación documental**.

Requisitos relacionados: **RF-04, RF-05, RF-06, RF-08, RF-16, RF-17**

### 3.3 Detección de vehículos sin autorización y alertas

El documento reporta que el **64%** consideró muy importante recibir una alerta ante la detección de un vehículo no autorizado y que el **34%** adicional la consideró importante. Estos porcentajes, el tamaño exacto de la muestra y su correspondencia con preguntas concretas quedan **pendientes de validación documental**.

Requisitos relacionados: **RF-13, RF-14, RF-15, RF-18, RF-19**

---

## 4. Definición de requerimiento funcional

Un **requerimiento funcional** es una declaración que especifica una función, servicio o comportamiento que un sistema debe proporcionar para satisfacer las necesidades de sus usuarios o los objetivos del negocio.

En VIGIA Vision Systems, los requerimientos funcionales establecen los comportamientos esperados para supervisar accesos vehiculares, registrar eventos, consultar información y generar alertas bajo las condiciones definidas para el sistema. Cada requisito describe **qué debe hacer el sistema**, no cómo se implementará técnicamente.

## 5. Criterios generales de verificación

Los requisitos funcionales deberán verificarse mediante pruebas, inspección o demostración, según corresponda:

- **Captura y detección:** configurar una cámara y un área de detección, presentar vehículos dentro y fuera del área, y comprobar que se registren únicamente los comportamientos previstos.
- **Reconocimiento y estados:** utilizar evidencias con matrícula legible, ilegible y sin coincidencia para comprobar que el sistema diferencie los estados definidos en la sección 1.1.
- **Registros y consultas:** crear o actualizar registros de vehículos, generar eventos y comprobar que la consulta y los filtros por fecha y matrícula devuelvan la información disponible.
- **Autorización y alertas:** usar registros con y sin datos suficientes de vigencia para comprobar que una coincidencia no se marque automáticamente como autorización vigente y que las condiciones de alerta se reflejen visualmente.
- **Evidencia:** comprobar que los eventos y las alertas muestren los datos y archivos disponibles, sin exigir información que no haya podido obtenerse durante el procesamiento.

Los resultados de estas verificaciones deberán documentarse durante las pruebas del sistema. Este documento no constituye evidencia de que los requisitos ya estén implementados o aprobados.
