# VIGIA-ENV-RECOVERY-03 — Verificación de Docker y Restauración de PostgreSQL

## Control Documental
- **Identificador:** `VIGIA-ENV-RECOVERY-03`
- **Fase:** Fase 1 — Hardening de Infraestructura y Preparación de Validación Física
- **Fecha de Ejecución:** 8 de noviembre de 2026
- **Naturaleza de la Actividad:** Verificación de daemon Docker, restauración y validación de almacenamiento PostgreSQL (Solo lectura de esquema; sin operaciones destructivas ni alteración de Changarro)
- **Dictamen:** **A — PostgreSQL restaurado y verificado**

---

## 1. Fase A — Verificación de Docker

### 1.1 Ejecución de `docker info`
Tras el encendido de Docker Desktop, se ejecutó la consulta de información del daemon:

```text
Client:
 Version:    29.1.3
 Context:    desktop-linux
 Debug Mode: false

Server:
 Containers: 6
  Running: 6
  Paused: 0
  Stopped: 0
 Images: 6
 Server Version: 29.1.3
 Storage Driver: overlayfs
 OSType: linux
 Architecture: x86_64
 Kernel Version: 6.6.87.2-microsoft-standard-WSL2
 Operating System: Docker Desktop
```

- **Respuesta del Daemon:** **OPERATIVO (Código de salida 0).**
- **Contexto Activo:** `desktop-linux`.
- **Tipo de Contenedores:** Linux containers bajo WSL2.
- **Servicios Definidos para VIGÍA:** Exclusivamente el servicio de base de datos relacional en [`BD/compose.yaml`](file:///c:/GEST.PROY.TI/Software/BD/compose.yaml):
  - Contenedor: `vigia-db`
  - Imagen: `postgres:16-alpine`
  - Mapeo de Puertos: `127.0.0.1:5434:5432`

---

## 2. Fase B — Verificación del Almacenamiento

### 2.1 Inspección del Volumen `vigia_pgdata`
Se ejecutó `docker volume inspect vigia_pgdata`:

```json
[
    {
        "CreatedAt": "2026-10-31T17:08:10Z",
        "Driver": "local",
        "Labels": {
            "com.docker.compose.config-hash": "b899db46e07dc7c6c88fb9ce53a0e7388f9253cf18676f106e1a85d5c9a73a7a",
            "com.docker.compose.project": "bd",
            "com.docker.compose.version": "5.0.0",
            "com.docker.compose.volume": "vigia_pgdata"
        },
        "Mountpoint": "/var/lib/docker/volumes/vigia_pgdata/_data",
        "Name": "vigia_pgdata",
        "Options": null,
        "Scope": "local"
    }
]
```

- **Existencia:** Confirmada (`local/vigia_pgdata`, creado el 31/10/2026).
- **Referencia en Compose:** Declarado como volumen nombrado `vigia_pgdata` montado en `/var/lib/postgresql/data`.
- **Integridad:** El volumen no fue eliminado, recreado ni formateado. Todos los datos históricos se conservaron intactos.

---

## 3. Fase C — Arranque Controlado de PostgreSQL

### 3.1 Levantamiento del Contenedor `vigia-db`
Se ejecutó `.\vigia.ps1 db-up` vinculando el archivo de variables `.env` (puerto `5434` en host hacia `5432` en contenedor):

```powershell
docker compose --env-file .env -f BD/compose.yaml up -d
```

Salida del comando:
```text
Container vigia-db Recreate
Container vigia-db Recreated
Container vigia-db Starting
Container vigia-db Started
```

### 3.2 Estado del Contenedor (`docker compose ps`)
```text
NAME       IMAGE                COMMAND                  SERVICE   CREATED          STATUS                    PORTS
vigia-db   postgres:16-alpine   "docker-entrypoint.s…"   db        12 seconds ago   Up 11 seconds (healthy)   127.0.0.1:5434->5432/tcp
```

- **Mapeo de Red:** `127.0.0.1:5434 -> 5432/tcp`.
- **Salud del Contenedor:** `healthy`.
- **Aislamiento de Puertos:** Coexiste de manera 100% independiente con Changarro (`127.0.0.1:5433`).

### 3.3 Prueba de Conexión (`check_connection.ps1`)
Se ejecutó `.\vigia.ps1 db-check`:

```text
 current_database | current_user |                                         version                                          
------------------+--------------+------------------------------------------------------------------------------------------
 vigia_db         | vigia_admin  | PostgreSQL 16.15 on x86_64-pc-linux-musl, compiled by gcc (Alpine 15.2.0) 15.2.0, 64-bit
(1 row)

Conexión verificada correctamente.
```

---

## 4. Fase D — Inspección de Solo Lectura del Esquema

Se realizó una inspección exhaustiva de solo lectura mediante consulta SQL directa a `vigia_db`:

### 4.1 Tablas Existentes (Esquema `public`)
Total de 18 tablas detectadas e íntegras:
- `accion_iluminacion`, `administrativo`, `alerta`, `alumno`, `area_vision`
- `camara`, `camara_credencial`, `camera_pairing_request`, `carrera`, `deteccion`
- `evento_acceso`, `evento_sensor`, `persona`, `persona_vehiculo`, `schema_version`
- `sensor`, `usuario`, `vehiculo`

### 4.2 Historial de Migraciones (`schema_version`)
Las 5 migraciones históricas se encuentran aplicadas con checksums válidos:
1. `V000` — `V000__init_database.sql` (31/10/2026)
2. `V001` — `V001__baseline_schema.sql` (31/10/2026)
3. `V002` — `V002__triggers.sql` (31/10/2026)
4. `V003` — `V003__seed_data.sql` (31/10/2026)
5. `V004` — `V004__enrolamiento_camaras_qr.sql` (02/11/2026)

*No se requirió ejecutar migraciones ni seed adicional.*

### 4.3 Usuarios de Prueba Verificados
- `admin_dev`: Rol `ADMINISTRADOR`, Estado `activo=True`, UUID `00000000-0000-0000-0002-000000000001`
- `guardia_dev`: Rol `OPERADOR` (Guardia), Estado `activo=True`, UUID `00000000-0000-0000-0002-000000000002`

### 4.4 Cámaras y Topología Registrada
- `CAM-ENTRADA`: Cámara Carril Entrada (`uri_stream: push://cam-entrada`, `activa=True`) con área `ROI-ENT` (`ENTRADA`).
- `CAM-SALIDA`: Cámara Carril Salida (`uri_stream: push://cam-salida`, `activa=True`) con área `ROI-SAL` (`SALIDA`).

---

## 5. Fase E — Verificación de TLS, Red y Puertos

### 5.1 Certificado Activo de Servidor ([`certs/vigia_cert.pem`](file:///c:/GEST.PROY.TI/Software/VIGIA_Vision_Systems/certs/vigia_cert.pem))
- **Sujeto:** `CN=VIGIA LAN Server (10.159.253.185), O=VIGIA Vision Systems, C=MX`
- **Emisor:** `CN=VIGIA Local Root CA, OU=Seguridad e Infraestructura LAN, O=VIGIA Vision Systems, C=MX`
- **Validez:** `06/11/2026 19:16:20 UTC` hasta `04/02/2027 19:21:20 UTC` (**Vigente**).
- **SAN Reales:** `['localhost', '127.0.0.1', '10.159.253.185']`.
- **URL de Revocación (CDP):** `http://10.159.253.185:5080/api/v1/tls/ca.crl`.
- **Observación de Red:** La IP de la máquina host es actualmente `192.168.1.76`. El acceso local vía `https://127.0.0.1:5001/app` es 100% válido y seguro. En apego a la directiva, el certificado no fue regenerado.

### 5.2 Estado de Puertos
- **Puerto 5434 (PostgreSQL VIGÍA):** **ACTIVO / OPERATIVO** (`vigia-db`, PostgreSQL 16.15).
- **Puerto 5001 (Backend HTTPS VIGÍA):** **LIBRE / LISTO** (No iniciado aún, en apego estricto a las restricciones).
- **Puerto 5080 (Servidor CRL HTTP):** Configurado y disponible.
- **Puerto 5000 (Changarro App):** **ACTIVO / INTACTO** (PID 20404).
- **Puerto 5433 (Changarro PostgreSQL):** **ACTIVO / INTACTO** (PID 36484).

---

## 6. Tabla de Evidencias de Comandos

| Comando Ejecutado | Código de Retorno | Evidencia / Diagnóstico |
| :--- | :--- | :--- |
| `docker info` | `0` | Daemon respondiendo, contexto `desktop-linux`, versión 29.1.3 |
| `docker volume inspect vigia_pgdata` | `0` | Volumen local intacto (`CreatedAt: 2026-10-31`) |
| `.\vigia.ps1 db-up` | `0` | Contenedor `vigia-db` recreado con mapeo `127.0.0.1:5434->5432` |
| `.\vigia.ps1 db-check` | `0` | Conexión exitosa a `vigia_db` como `vigia_admin` en PostgreSQL 16.15 |
| `SELECT * FROM schema_version` | `0` | 5 migraciones aplicadas (`V000`..`V004`) |
| `SELECT username, rol FROM usuario` | `0` | `admin_dev` (ADMINISTRADOR) y `guardia_dev` (OPERADOR) presentes |
| `SELECT codigo FROM camara` | `0` | `CAM-ENTRADA` y `CAM-SALIDA` activas |
| `socket.connect(('127.0.0.1', 5001))` | `10061 (Free)` | Backend VIGÍA apagado, puerto listo para arranque |
| `socket.connect(('127.0.0.1', 5000))` | `0 (Busy)` | Changarro App intacta |
| `socket.connect(('127.0.0.1', 5433))` | `0 (Busy)` | Changarro PostgreSQL 18 intacto |

---

## 7. Dictamen Final

```
================================================================================
DICTAMEN: A — PostgreSQL restaurado y verificado.
================================================================================
```

### Justificación Técnica:
1. **Docker y PostgreSQL Operativos:** El motor de Docker respondió satisfactoriamente, el contenedor `vigia-db` se levantó de forma limpia y la base de datos respondió al script oficial de comprobación `.\vigia.ps1 db-check`.
2. **Datos y Esquema Completos:** El volumen persistente `vigia_pgdata` preservó la totalidad del esquema (18 tablas, 5 migraciones), los roles de usuario (`admin_dev` y `guardia_dev`) y las cámaras base (`CAM-ENTRADA` y `CAM-SALIDA`).
3. **Aislamiento Total Comprobado:** Ningún proceso ni recurso de Changarro fue perturbado; VIGÍA opera en el puerto host `5434` sin interferencias.
4. **Entorno Listo:** El puerto `5001` está libre y disponible para el arranque del backend HTTPS cuando sea autorizado.
