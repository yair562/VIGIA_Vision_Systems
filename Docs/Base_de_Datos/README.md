# Base de Datos — VIGIA Vision Systems

Bienvenido al directorio de documentación técnica, arquitectónica y de diseño de la **Base de Datos** de VIGIA.

---

## 1. Propósito

Este directorio centraliza las especificaciones, modelos y artefactos correspondientes a la capa de persistencia y datos de VIGIA, abarcando desde los modelos conceptuales iniciales hasta los modelos lógicos, físicos y scripts DDL/migraciones para el motor de base de datos objetivo (**PostgreSQL**).

---

## 2. Documentos Disponibles

| Documento | Versión | Estado | Descripción |
| :--- | :---: | :---: | :--- |
| **[01 — Modelo Conceptual de Base de Datos V1](./01_modelo_conceptual_v1.md)** | **V1** | Propuesto | Define las 12 entidades principales, relaciones, reglas de negocio y flujos de vehículos conocidos vs. desconocidos. |

---

## 3. Próximos Entregables Técnicos

A partir del modelo conceptual V1 se desarrollarán los siguientes artefactos:
1. **Modelo Lógico (V1):** Tipos de datos estandarizados, normalización, definiciones de nulabilidad y restricciones.
2. **Modelo Físico y DDL (PostgreSQL):** Esquemas relacionales, llaves primarias/foráneas, índices de búsqueda por placa, políticas de integridad referencial (`ON DELETE` / `ON UPDATE`), y optimización de consultas históricas.
3. **Scripts de Sembrado (Seed) y Migraciones:** Inserción de datos iniciales para roles, carreras, usuarios de prueba y cámaras.
