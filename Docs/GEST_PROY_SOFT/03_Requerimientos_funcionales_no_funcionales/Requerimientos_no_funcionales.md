# 03.2 — Requerimientos No Funcionales

**Proyecto:** VIGIA Vision Systems  
**Área:** Gestión de Proyectos de Software / Ingeniería de Requisitos  
**Responsable del Entregable:** Yair  
**Puesto / Rol del Responsable:** Ingenieros de Software + Ing. de Diseño Eléctrico  
**Versión:** 1.2  
**Fecha:** 23 de septiembre de 2026  

---

## 1. Catálogo de Requerimientos No Funcionales (RNF)

| ID | Requerimiento no funcional |
| :---: | :--- |
| **RNF-01** | Utilizar autenticación mediante usuario y contraseña para validar la identidad de cada usuario. |
| **RNF-02** | Utilizar control de acceso basado en roles (RBAC) para asignar permisos según las funciones autorizadas para cada usuario. |
| **RNF-03** | Almacenar las contraseñas utilizando Argon2id para evitar su almacenamiento en texto plano. |
| **RNF-04** | Utilizar AES-256 para cifrar la información sensible almacenada en la base de datos. |
| **RNF-05** | Utilizar HTTPS mediante TLS 1.3 para proteger la información transmitida entre los componentes del sistema. |
| **RNF-06** | Restringir el acceso a los registros de personas, vehículos y eventos mediante los permisos asignados a cada rol. |
| **RNF-07** | Mantener la integridad de los registros mediante validaciones de datos y restricciones de integridad en la base de datos. |
| **RNF-08** | Registrar los errores y fallos relevantes mediante un sistema de logs para facilitar el diagnóstico y mantenimiento. |
| **RNF-09** | Mantener una arquitectura modular que permita incorporar nuevos componentes de procesamiento o visión artificial sin modificar completamente el sistema. |
| **RNF-10** | Realizar copias de respaldo periódicas de la información almacenada y permitir su recuperación ante pérdida de datos. |
| **RNF-11** | Presentar la información de supervisión mediante una interfaz clara, consistente y comprensible para el personal autorizado. |
| **RNF-12** | Limitar la recopilación de datos personales a la información necesaria para ejecutar las funciones definidas dentro del alcance de VIGIA. |

---

## 2. Tecnologías y Criterios Técnicos de Seguridad

Los requisitos no funcionales incorporan tecnologías y estándares reconocidos de la industria para garantizar la seguridad, integridad y mantenibilidad del sistema:

* **RBAC (*Role-Based Access Control*):** Modelo de control de acceso que asigna privilegios mínimos indispensables según el puesto y responsabilidad de cada usuario (operador, administrador, auditor).
* **Argon2id:** Algoritmo estándar de hashing de contraseñas de última generación (ganador del *Password Hashing Competition*), diseñado para resistir ataques por fuerza bruta basados en GPU y ASIC.
* **AES-256 (*Advanced Encryption Standard* con clave de 256 bits):** Mecanismo de cifrado simétrico robusto para proteger datos confidenciales y sensibles en reposo (*data at rest*).
* **TLS 1.3 / HTTPS:** Protocolo criptográfico para asegurar canales de comunicación en tránsito (*data in transit*), reduciendo la latencia de handshake y eliminando suites de cifrado obsoletas.
* **Sistema de Logs:** Registro estructurado y cronológico de eventos técnicos, excepciones y anomalías operativas para trazabilidad y auditoría forense.
* **Restricciones de Integridad en BD:** Reglas a nivel de motor de base de datos (claves primarias, foráneas, constraints de unicidad y no nulidad) para impedir la corrupción o inconsistencia de datos.
* **Mecanismos de Backup y Recuperación:** Políticas de respaldo periódico y procedimientos verificables de restauración ante fallos de hardware o contingencias lógicas.