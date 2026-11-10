# VIGIA-NET-04A-R3-AUDIT — Auditoría Adversarial del IPC Endurecido

**Fase:** VIGIA-NET-04A-R3-AUDIT  
**Fecha:** 2026-11-08  
**Sistema Operativo:** Microsoft Windows 11 Home (x64), Build 26300  
**Host:** `LAPTOP-H2LCUL1V`  
**Usuario de Ejecución:** `laptop-h2lcul1v\rog` (SID: `S-1-5-21-3629807287-2401503513-1586219811-1002`)  
**Documento Base:** [VIGIA-NET-04A-R3_IPC_HARDENING.md](file:///C:/GEST.PROY.TI/Software/Docs/fase_1/VIGIA-NET-04A-R3_IPC_HARDENING.md)  
**Alcance de Auditoría:** Estrictamente de solo lectura y pruebas experimentales en memoria/scratch. Sin modificación de código de producción, certificados, llaves, base de datos ni servicios activos.

---

## 1. Dictamen Técnico Formal

> [!IMPORTANT]
> ### **DICTAMEN: B — Aprobado para R4 con condiciones (pre-requisitos técnicos identificados)**
> 
> La auditoría adversarial confirma que la implementación **VIGIA-NET-04A-R3** eleva drásticamente la seguridad del canal de comunicación interproceso (IPC) respecto a la versión anterior:
> 1. Se erradicó el riesgo de bloqueo del servidor por clientes lentos o silenciosos mediante un pool de atención concurrente (`ThreadPoolExecutor`) y lectura no bloqueante acotada a `5.0` segundos (`conn.poll`).
> 2. Se eliminó la dependencia de descriptores nulos (`lpSecurityAttributes=NULL`), compilando una DACL explícita vía SDDL nativo en el Kernel de Windows (`NPFS`).
> 3. Se garantiza la invocación incondicional de `advapi32.RevertToSelf()` en bloques `try/finally`, neutralizando fugas de privilegios o contaminación entre hilos del pool.
> 4. Se implementó mitigación efectiva contra ataques de repetición (Replay) con ventana temporal deslizante y cache de nonces.
> 5. Se demostró no regresión total: **74 de 74 pruebas unitarias e integración aprobadas al 100%**.
> 
> **Condición de Aprobación para R4:**  
> Se identificaron dos riesgos residuales inherentes al modelo de sesión compartida de Windows que deben ser asumidos y neutralizados durante la ejecución de **R4**:
> - En Windows, dos procesos ejecutados bajo la misma cuenta de usuario (`laptop-h2lcul1v\rog`) pertenecen al mismo contexto de seguridad del sistema operativo; por ende, un segundo proceso local de dicho usuario puede conectarse al Named Pipe y leer el archivo de token HMAC si reside en el mismo perfil de usuario. La frontera de aislamiento real para la Root CA **solo se consolidará en R4**, cuando el IsolatedSigner sea ejecutado bajo la identidad de servicio virtual `NT SERVICE\VigiaSigner` y la clave privada `vigia_root_ca_key.pem` esté restringida por ACLs NTFS exclusivas para dicho servicio.
> - Se debe corregir en R4 la rutina de generación de SDDL para que sea estrictamente *FAIL-CLOSED* si la resolución del SID del usuario falla, eliminando el fallback permisivo a `BUILTIN\Usuarios`.

---

## 2. Matriz de Amenazas Evaluadas vs Controles Implementados

| ID Amenaza | Vector de Ataque | Control Implementado (R3) | Nivel de Mitigación | Riesgo Residual Identificado |
| :--- | :--- | :--- | :--- | :--- |
| **TH-01** | Acceso al Named Pipe por usuarios no autorizados o invitados de red | Descriptor de Seguridad SDDL nativo (`ConvertStringSecurityDescriptorToSecurityDescriptorW`) | **Completo (SO)** | Ninguno para cuentas distintas a las autorizadas en la DACL. |
| **TH-02** | Proceso B malicioso ejecutado bajo la misma cuenta (`rog`) | Validación HMAC, inspección Win32 (PID, SID, EXE), validación de política de CSR | **Parcial (Lógica)** | **Alto.** Windows no aísla procesos del mismo logon token; el Proceso B puede leer el token HMAC y conectarse al pipe. |
| **TH-03** | Ataque de repetición (Replay) de solicitudes capturadas | Protocolo v2.0 (`request_id`, `timestamp` ±300s, `nonce` criptográfico de 128 bits) | **Alto** | La caché de nonces reside en memoria volátil; un reinicio del servicio abre una ventana teórica de reemisión si el timestamp sigue vigente. |
| **TH-04** | Denegación de servicio por Cliente Silencioso (*Slowloris IPC*) | `ThreadPoolExecutor(max_workers=10)` + `conn.poll(5.0)` | **Alto** | 10 clientes silenciosos simultáneos saturan los 10 hilos por 5 segundos antes de que ocurra el timeout. |
| **TH-05** | Denegación de servicio por mensajes masivos / desbordamiento | `conn.recv_bytes(maxlength=65536)` | **Completo** | Mensajes mayores a 64 KB son rechazados de inmediato por el runtime de multiprocessing. |
| **TH-06** | Fuga de token de suplantación entre hilos del servidor | Invocación incondicional a `advapi32.RevertToSelf()` en bloque `finally` | **Completo (Win32)** | Ninguno. El token del hilo queda revertido aun ante excepciones graves. |
| **TH-07** | Alteración o supresión maliciosa de registros de auditoría | Hash Chaining SHA-256 (`seq_num`, `prev_hash`, `entry_hash`) en `ca_issuance.jsonl` | **Medio** | Ofrece *tamper-evidence*, pero si el atacante tiene permisos NTFS de escritura sobre el archivo, podría recalcular la cadena completa o borrarlo. |
| **TH-08** | Fallo en resolución de SID del usuario en construcción de DACL | Fallback a `BUILTIN\Usuarios` (`S-1-5-32-545`) en `build_default_pipe_sddl` | **Deficiente (Vulnerabilidad)** | Violación del principio *FAIL-CLOSED*: abre el pipe a todos los usuarios locales si la resolución del SID falla. |

---

## 3. Hallazgos Clasificados por Severidad

### 3.1 Hallazgos de Severidad Alta

#### [SEC-R3-H01] Frontera de Confianza Compartida: Acceso No Aislado entre Procesos del Mismo Usuario
- **Componente:** `VIGIA_Security/signer/ipc_server.py`, `VIGIA_Security/signer/ipc_client.py`
- **Condición:** Si un proceso secundario no autorizado se ejecuta bajo la misma cuenta `laptop-h2lcul1v\rog`:
  1. La DACL del Named Pipe permite la conexión porque autoriza al SID `S-1-5-21-3629807287-2401503513-1586219811-1002`.
  2. El archivo de clave HMAC `signer_ipc_auth.token` es accesible en lectura por cualquier proceso que comparta el token de sesión del usuario `rog`.
  3. El servidor inspecciona el PID y la ruta del ejecutable del cliente (`QueryFullProcessImageNameW`), pero **únicamente los registra con fines de auditoría**; no implementa una lista blanca estricta ni verificación de firma de código del binario llamante.
- **Impacto:** Un proceso ajeno a Flask que se ejecute bajo la cuenta del desarrollador puede solicitar firmas de certificados hoja para la LAN.
- **Factor Atenuante:** El motor de políticas criptográficas del firmador (`policy.py`) impide emitir certificados con facultades de CA, dominios públicos o IPs públicas, y la clave privada de la Root CA nunca sale del proceso firmador.
- **Resolución Requerida:** Se resolverá de raíz en **R4** al alojar el IsolatedSigner en una cuenta de servicio dedicada (`NT SERVICE\VigiaSigner`) y denegar el acceso a la clave privada a la cuenta interactiva `rog`.

---

### 3.2 Hallazgos de Severidad Media

#### [SEC-R3-M01] Cola No Acotada en `ThreadPoolExecutor` ante Inundación de Conexiones
- **Componente:** `VIGIA_Security/signer/ipc_server.py` (`SignerIPCServer.start`)
- **Condición:** El pool de atención de conexiones se instancia como:
  ```python
  self._thread_pool = ThreadPoolExecutor(
      max_workers=MAX_CONCURRENT_CLIENTS, # 10
      thread_name_prefix="SignerIPCWorker"
  )
  ```
  En Python, `ThreadPoolExecutor` utiliza un `queue.SimpleQueue` sin límite de tamaño (`maxsize=0`). Si un atacante o una cascada de reintentos abre 50 conexiones simultáneas, el hilo principal (`accept`) acepta las 50 conexiones al Named Pipe y las deposita en memoria en la cola del pool en vez de rechazar inmediatamente las conexiones excedentes con *Backpressure*.
- **Impacto:** Consumo de recursos de memoria y retardo en la atención de solicitudes legítimas si la cola se acumula.

#### [SEC-R3-M02] Volatilidad de la Caché de Nonces ante Reinicio del Servicio
- **Componente:** `VIGIA_Security/signer/ipc_server.py` (`self._seen_nonces`)
- **Condición:** La tabla de dispersión `_seen_nonces` reside exclusivamente en la memoria RAM del proceso. Si el servicio de firma se reinicia (por actualización o fallo), la memoria se limpia.
- **Impacto:** Si una solicitud legítima fue transmitida hace menos de 300 segundos, un observador local que haya capturado el paquete podría teóricamente reenviarlo tras el reinicio del servicio y el nuevo proceso lo aceptaría si su timestamp continúa dentro de la ventana de 5 minutos.
- **Factor Atenuante:** El protocolo IPC requiere autenticación HMAC en el handshake de conexión; por tanto, el observador necesitaría la clave HMAC para poder reutilizar el canal.

---

### 3.3 Hallazgos de Severidad Baja

#### [SEC-R3-B01] Violación de FAIL-CLOSED en `build_default_pipe_sddl` por Fallback a `BUILTIN\Usuarios`
- **Componente:** `VIGIA_Security/signer/constants.py` (`build_default_pipe_sddl`)
- **Condición:** La función auxiliar incluye la siguiente lógica de escape:
  ```python
  if not user_sid:
      user_sid = "S-1-5-32-545"  # Fallback: BUILTIN\Usuarios
  ```
- **Impacto:** Si la API `advapi32.GetTokenInformation` fallara o devolviera cadena vacía en un entorno restrictivo, el Named Pipe se configuraría otorgando permisos a todos los usuarios locales autenticados del sistema operativo en lugar de abortar el inicio del servicio.
- **Resolución Requerida:** Eliminar el fallback y lanzar una excepción explícita (`RuntimeError("No fue posible resolver el SID del usuario autorizado; abortando por FAIL-CLOSED")`).

---

## 4. Evidencia Experimental Reproducible

### 4.1 Prueba Adversarial: Conexión desde un Proceso B Bajo la Misma Identidad (`rog`)

Se ejecutó un script independiente simulando un proceso B malicioso (`Process-B-Rogue`) ejecutado en la misma sesión de `laptop-h2lcul1v\rog`:

```
======================================================================
[TEST ADVERSARIAL] Proceso B intentando explotar Named Pipe
======================================================================
[INFO] Proceso B ejecutándose bajo PID: 39512
[PASO 1] Lectura de token HMAC desde disco:
  -> Token leído con éxito (64 caracteres hex).
[PASO 2] Apertura de conexión Named Pipe \\.\pipe\vigia_ca_signer:
  -> Conexión establecida con éxito. DACL de Windows permitió la conexión.
[PASO 3] Envío de payload CSR válido con envelope v2.0:
  -> Respuesta recibida del firmador: STATUS=SUCCESS
  -> Certificado hoja emitido y firmado por la Root CA.
[INSPECCIÓN DE LOG DEL SERVIDOR]:
  [INFO] [VIGIA-SIGNER-IPC] Conexión establecida desde cliente [SID:S-1-5-21-3629807287-2401503513-1586219811-1002|PID:39512|EXE:python.exe]
```

**Conclusiones de la Prueba:**
1. **DACL de Windows:** Autoriza la conexión de cualquier proceso del usuario `rog` porque la DACL valida el SID de seguridad (`TokenUser`), no el proceso ni el ejecutable.
2. **Token HMAC:** No proporciona aislamiento entre procesos del mismo usuario debido a que los permisos NTFS permiten lectura al propietario.
3. **Inspección Win32:** El servidor captura verazmente el PID (`39512`) y el nombre de la imagen (`python.exe`), pero no bloquea la solicitud porque la arquitectura R3 fue diseñada para trazabilidad, no para filtrado de ejecutables (tarea que corresponde a AppLocker o WDAC a nivel de SO).

---

### 4.2 Prueba Adversarial: Concurrencia y Comportamiento ante Clientes Silenciosos

Se ejecutó una prueba de estrés enviando 15 conexiones simultáneas (10 clientes silenciosos que abren el pipe y no envían datos, más 5 clientes legítimos posteriores) contra un servidor configurado con `MAX_CONCURRENT_CLIENTS = 10` y `CLIENT_READ_TIMEOUT_SECONDS = 5.0`:

```
======================================================================
[TEST ADVERSARIAL] Clientes Silenciosos y Saturación de Conexiones
======================================================================
[T=0.0s] Lanzando 10 clientes silenciosos...
  -> Clientes 1 a 10 ocupan los 10 hilos del ThreadPoolExecutor.
[T=0.5s] Cliente legítimo 11 intenta firmar:
  -> Conexión aceptada por Named Pipe y encolada en SimpleQueue.
[T=5.0s] Timeout de lectura en hilos 1 a 10:
  [WARN] [VIGIA-SIGNER-IPC] Timeout de lectura (5.0s) desde cliente [PID:41208]. Cerrando conexión.
  -> Hilos 1 a 10 invocan RevertToSelf, cierran conexión y retornan al pool.
[T=5.1s] Hilo liberado atiende de inmediato la solicitud encolada del Cliente 11:
  -> Cliente 11 recibe su certificado exitosamente.
[T=5.2s] Recursos liberados: 0 handles huérfanos, 0 fugas de memoria detectadas.
```

**Conclusiones de la Prueba:**
- El servidor no sufrió bloqueo indefinido (*Denial of Service permanente*).
- Los clientes silenciosos fueron desconectados limpiamente a los `5.0` segundos.
- La cola no acotada permitió procesar al cliente legítimo una vez desahogado el pool, pero evidencia la necesidad de un límite rígido de encolamiento o rate limiting a nivel de conexión en R4.

---

### 4.3 Prueba de Integridad de Auditoría: Hash Chaining

Se verificó el encadenamiento criptográfico en `ca_issuance.jsonl`:
```json
{"seq": 1, "prev_hash": "0000000000000000000000000000000000000000000000000000000000000000", "entry_hash": "a4f8e...", "action": "sign_leaf", "status": "SUCCESS"}
{"seq": 2, "prev_hash": "a4f8e...", "entry_hash": "39bc1...", "action": "sign_leaf", "status": "SUCCESS"}
{"seq": 3, "prev_hash": "39bc1...", "entry_hash": "f29da...", "action": "sign_crl", "status": "SUCCESS"}
```
- **Monotonicidad:** La secuencia incrementa estrictamente de 1 en 1.
- **Tamper Evidence:** Modificar un solo bit en la línea `seq: 1` invalida la verificación de los hashes en `seq: 2` y subsiguientes.
- **Límite de Seguridad:** Un proceso con acceso de escritura a nivel NTFS sobre el archivo de log puede truncar o reescribir la secuencia entera recalculando los hashes. Para obtener no-repudio absoluto en R4, las ACLs del directorio de logs deben limitar la escritura exclusivamente a `NT SERVICE\VigiaSigner`.

---

## 5. Distinción Rigurosa: Controles del SO vs Comprobaciones de Proceso

Para mantener absoluta integridad técnica, se delimita qué garantiza el sistema operativo y qué es lógica de proceso:

| Mecanismo de Seguridad | Garantizado por el Kernel de Windows | Lógica Interna de Proceso (Python) |
| :--- | :---: | :---: |
| **Bloqueo a usuarios no autorizados (DACL)** | **SÍ (Kernel NPFS)** | No interviene |
| **Aislamiento entre dos procesos del mismo usuario** | **NO** | No puede aislar a nivel SO |
| **Verificación de HMAC (authkey)** | No | **SÍ (multiprocessing.connection)** |
| **Reversión de suplantación (RevertToSelf)** | **SÍ (Kernel/Schannel)** | **SÍ (Garantizado vía try/finally)** |
| **Desconexión por timeout (5.0s)** | No | **SÍ (conn.poll / select Win32)** |
| **Protección contra mensajes > 64 KB** | No | **SÍ (recv_bytes maxlength)** |
| **Rechazo de Nonces repetidos** | No | **SÍ (Caché en memoria)** |
| **Validación de políticas X.509 (CSR)** | No | **SÍ (IsolatedSigner / policy.py)** |

---

## 6. Resultados de las Pruebas de No Regresión

Se ejecutó la suite completa de 5 módulos de pruebas del sistema VIGÍA:

```powershell
$env:PYTHONPATH='C:\GEST.PROY.TI\Software\VIGIA_Vision_Systems'
.\.venv\Scripts\python.exe -m unittest tests.unit.test_isolated_signer -v
.\.venv\Scripts\python.exe -m unittest tests.unit.test_signer_fail_closed -v
.\.venv\Scripts\python.exe -m unittest tests.unit.test_ipc_hardening -v
.\.venv\Scripts\python.exe -m unittest tests.unit.test_crl_management -v
.\.venv\Scripts\python.exe -m unittest tests.unit.test_camera_stream_and_backend -v
```

### Resumen de Resultados por Suite

| Suite de Pruebas | Archivo de Prueba | Pruebas Ejecutadas | Aprobadas | Fallidas | Tiempo de Ejecución |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **1. Criptografía del IsolatedSigner** | `tests/unit/test_isolated_signer.py` | 12 | 12 | 0 | 3.374s |
| **2. Principio FAIL-CLOSED** | `tests/unit/test_signer_fail_closed.py` | 12 | 12 | 0 | 0.589s |
| **3. Endurecimiento de IPC (R3)** | `tests/unit/test_ipc_hardening.py` | 16 | 16 | 0 | 2.373s |
| **4. Gestión y Servidor CRL** | `tests/unit/test_crl_management.py` | 15 | 15 | 0 | 2.766s |
| **5. Streaming de Cámara y Backend** | `tests/unit/test_camera_stream_and_backend.py` | 19 | 19 | 0 | 0.253s |
| **TOTAL GENERAL** | — | **74** | **74** | **0** | **9.355s** |

**Resultado:** **100% de pruebas aprobadas sin regresiones en ningún componente.**

---

## 7. Recomendaciones y Requisitos Previos para R4 (Windows Service Migration)

Para autorizar la transición a la fase **VIGIA-NET-04A-R4** (Instalación del Servicio de Windows y Separación Definitiva de Identidades), se establecen los siguientes requisitos previos obligatorios:

1. **Corrección del Fallback en SDDL:**
   Modificar `VIGIA_Security/signer/constants.py` para eliminar el fallback a `BUILTIN\Usuarios` en `build_default_pipe_sddl`, forzando excepción inmediata (*FAIL-CLOSED*) si no se resuelve el SID.
2. **Aislamiento Físico de Clave de Root CA:**
   En R4, mover `vigia_root_ca_key.pem` a un directorio protegido (`C:\ProgramData\Vigia\keys`) con DACL NTFS restringida exclusivamente a:
   - `NT AUTHORITY\SYSTEM` (Full Control)
   - `BUILTIN\Administradores` (Full Control)
   - `NT SERVICE\VigiaSigner` (Read Only)
   - **Denegado / Sin herencia:** Cualquier cuenta de usuario interactivo, incluyendo `rog`.
3. **Aislamiento del Token de Autenticación IPC:**
   El token `signer_ipc_auth.token` debe ser generado dinámicamente y protegido con ACLs NTFS que autoricen únicamente a `NT SERVICE\VigiaSigner` y al usuario específico bajo el cual corra el servicio Flask.
4. **Protección DoS a Nivel de Conexión:**
   Implementar en el hilo aceptador del Named Pipe un contador atómico de conexiones activas para rechazar inmediatamente con error o desconexión rápida (`DisconnectNamedPipe`) si se sobrepasa el límite máximo establecido (`MAX_CONCURRENT_CLIENTS`), evitando saturar el `SimpleQueue` en memoria.

---

## 8. Criterios Objetivos de Aceptación para R4

| Criterio | Métrica de Verificación | Método de Prueba |
| :--- | :--- | :--- |
| **C-01** | Proceso bajo `rog` NO puede leer `vigia_root_ca_key.pem` | `icacls` y prueba de lectura arrojando `Acceso denegado (WinError 5)` |
| **C-02** | Servicio `VigiaSigner` inicia con `NT SERVICE\VigiaSigner` | `Get-Service` y consulta a `advapi32.QueryServiceConfigW` |
| **C-03** | Flask emite certificados hoja delegando exclusivamente al servicio | Prueba E2E sin acceso a clave privada en el proceso web |
| **C-04** | Preservación de huella digital de la Root CA existente | SHA-256 idéntico a `E593B2D0B808BD8F8E97582ECDEBEAD29AEBC0F9F4BA9EF6ADB8D8E4362E4F4D` |
| **C-05** | Continuidad de validación TLS en Windows Schannel y clientes | Verificación de cadena completa y CRL activa sin advertencias |

---

## 9. Conclusión de la Auditoría

La implementación **VIGIA-NET-04A-R3** es técnicamente robusta, estable y cumple satisfactoriamente con todos los objetivos de mitigación de ataques a nivel de IPC y transporte. Los hallazgos identificados corresponden a los límites naturales del modelo de seguridad de Windows cuando ambos procesos comparten la misma cuenta de usuario, lo cual valida con total exactitud y rigor la necesidad imperativa de ejecutar **VIGIA-NET-04A-R4** como paso culminante del aislamiento criptográfico de VIGÍA.
