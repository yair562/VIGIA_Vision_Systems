# VIGIA-NET-04A-AUDIT — Auditoría Adversarial del IsolatedSigner

**Fecha de Auditoría:** 2026-11-08  
**Tipo de Evaluación:** Auditoría Técnica de Seguridad Adversarial, Estrictamente de Solo Lectura  
**Alcance:** Paquete `VIGIA_Security.signer`, integración en `VIGIA_API/ingest_service.py`, permisos NTFS del sistema de archivos Windows y canal IPC Named Pipe  
**Entorno Evaluado:** Windows 11 / Windows Server, Host `LAPTOP-H2LCUL1V`, Usuario interactivo `laptop-h2lcul1v\rog`  

---

## 1. Resumen Ejecutivo y Dictamen

Se ha ejecutado una auditoría adversarial rigurosa e independiente para determinar si la clave privada de la Autoridad Certificadora Raíz (`certs/vigia_root_ca_key.pem`) se encuentra verdaderamente aislada del proceso Flask bajo las condiciones operativas reales de Windows.

### Dictamen Técnico Final
> [!CAUTION]
> ### **DICTAMEN: C — AISLAMIENTO NO DEMOSTRADO**
> **Justificación Inapelable (conforme a los criterios de evaluación):**
> 1. **Acceso directo comprobado en el SO:** El proceso Flask (ejecutándose bajo la cuenta de usuario activa `laptop-h2lcul1v\rog`) conserva acceso efectivo de **Lectura y Modificación Total** sobre `certs/vigia_root_ca_key.pem`. Las ACLs de NTFS vigentes en el almacén de producción son las heredadas del sistema (`BUILTIN\Usuarios:(RX)` y `NT AUTHORITY\Usuarios autentificados:(M)`).
> 2. **Ruta de firma local activa en producción:** Cuando el demonio `IsolatedSigner` o el Named Pipe no están disponibles, `VIGIA_API/ingest_service.py` **no implementa una política Fail-Closed**. En su lugar, ejecuta automáticamente un fallback silencioso que carga `vigia_root_ca_key.pem` directamente en la memoria de Flask y emite certificados y CRLs de forma local.
> 3. **Indiferenciación de identidades Windows:** Tanto Flask como el firmador ejecutan (o están configurados para ejecutar) bajo la misma cuenta de usuario. No existe un límite de seguridad a nivel de kernel/DACL entre ambos procesos.

---

## 2. Auditoría de Aislamiento del Sistema Operativo

### 2.1. Identidad Windows de los Procesos
- **Identidad interactiva activa:** `laptop-h2lcul1v\rog`
- **Nivel de integridad:** `Medium Mandatory Level` (`S-1-16-8192`)
- **Grupos efectivos:** `BUILTIN\Usuarios`, `NT AUTHORITY\Usuarios autentificados`, `NT AUTHORITY\INTERACTIVE`, `docker-users`.
- **Identidad de Flask:** Al invocarse mediante `python ingest_service.py` o tareas de fondo, hereda el token de seguridad del usuario `laptop-h2lcul1v\rog`.
- **Identidad de IsolatedSigner:** Al invocarse mediante `python -m VIGIA_Security.signer.daemon`, hereda idéntico token de seguridad.
- **Riesgo Identificado:** Al no implementarse una cuenta de servicio Windows dedicada (ej. `NT SERVICE\VigiaSigner` o `NT AUTHORITY\LocalService`), no existe frontera de aislamiento de procesos en el subsistema de seguridad de Windows (LSASS).

### 2.2. Permisos NTFS Reales (icacls) en Almacén de Certificados
Inspección directa realizada sobre los archivos de producción:

```
VIGIA_Vision_Systems\certs\vigia_root_ca_key.pem
    BUILTIN\Administradores:(I)(F)
    NT AUTHORITY\SYSTEM:(I)(F)
    BUILTIN\Usuarios:(I)(RX)
    NT AUTHORITY\Usuarios autentificados:(I)(M)
```

**Hallazgos de Permisos:**
- Todos los permisos son heredados `(I)` de la raíz del sistema de archivos.
- `NT AUTHORITY\Usuarios autentificados` posee permiso de **Modificación `(M)`**.
- `BUILTIN\Usuarios` posee permiso de **Lectura y Ejecución `(RX)`**.
- El script de configuración de ACLs (`setup_signer_acls.ps1`) **no ha sido aplicado sobre el entorno de producción**.
- **Análisis del script `setup_signer_acls.ps1` (Línea 55):**  
  El script contiene:
  ```powershell
  $currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
  & icacls "$caKeyPath" /grant:r "${currentUser}:(F)" | Out-Null
  ```
  Incluso si este script fuese ejecutado por el usuario `rog`, otorgaría control total explícito a `rog`. Dado que Flask corre como `rog`, Flask mantendría acceso de lectura/escritura completo a la clave privada.

### 2.3. Acceso Efectivo Comprobado
Prueba empírica de acceso ejecutada en el entorno:
- `os.access('certs/vigia_root_ca_key.pem', os.R_OK)` $\rightarrow$ **`True`**
- `os.access('certs/vigia_root_ca_key.pem', os.W_OK)` $\rightarrow$ **`True`**
- Existencia de `signer_ipc_auth.token` en producción $\rightarrow$ **`False`** (no inicializado en producción).
- Directorio `certs/audit/` en producción $\rightarrow$ **`False`** (no existe en producción).

---

## 3. Auditoría de Seguridad del Named Pipe e IPC

### 3.1. Creación del Named Pipe y Descriptor de Seguridad
En `VIGIA_Security/signer/ipc_server.py`:
```python
self._listener = Listener(self.pipe_name, "AF_PIPE", authkey=self.authkey)
```
- `multiprocessing.connection.Listener` invoca la API Win32 `CreateNamedPipeW` con `lpSecurityAttributes = NULL`.
- Al no proveer un descriptor de seguridad explícito (SDDL), Windows asigna la DACL por defecto del token de acceso del creador.
- **Consecuencia:** Cualquier proceso en la misma sesión de inicio de sesión o con privilegios de usuario estándar puede abrir un manipulador (handle) hacia el Named Pipe.

### 3.2. Mecanismo de Autenticación HMAC y Token
- La autenticación utiliza desafío-respuesta HMAC digest integrado en `multiprocessing.connection`.
- El secreto precompartido (`authkey`) reside en `certs/signer_ipc_auth.token`.
- **Vulnerabilidad de Almacenamiento:** Debido a las ACLs heredadas en `certs/`, cualquier proceso que ejecute bajo `rog` o como usuario autenticado en Windows puede leer `signer_ipc_auth.token`.
- **Capacidad de Solicitud Arbitraria:** Cualquier proceso local que lea el token puede conectarse al pipe y solicitar la firma de certificados o CRLs sin restricción adicional.

### 3.3. Verificación de PID vs. Autenticación de Proceso
En `VIGIA_Security/signer/ipc_server.py` (Líneas 88-126):
- El servidor consulta `kernel32.GetNamedPipeClientProcessId(handle, ctypes.byref(client_pid))`.
- El PID obtenido se formatea como `client_ident = f"PID:{client_pid}"`.
- **Riesgo:** El servidor **no valida** si el PID corresponde a un proceso Flask legítimo, ni verifica la ruta de su ejecutable, ni su firma digital, ni su token de seguridad. Conocer el PID solo sirve para logging forense posterior, no para control de acceso (DAC).

### 3.4. Concurrencia y Vulnerabilidad de Bloqueo (Denial of Service)
En `VIGIA_Security/signer/ipc_server.py` (Líneas 113-138):
- El bucle de servicio es **síncrono y monohilo**:
  ```python
  conn = self._listener.accept()
  req = conn.recv()
  ```
- No se configura un timeout en `conn.recv()`.
- La implementación de `Listener` en modo `AF_PIPE` de Python crea una única instancia del pipe (`nMaxInstances = 1`).
- **Prueba Adversarial Realizada:** Se conectó un cliente que omitió el envío de datos. Un segundo cliente intentó conectarse concurrentemente y falló de inmediato con:
  `FileNotFoundError: [WinError 2] The system cannot find the file specified` en `WaitNamedPipe`.
- **Impacto:** Un cliente lento, colgado o malicioso que mantenga abierta la conexión al Named Pipe bloquea indefinidamente todas las solicitudes de firma de VIGÍA y provoca que Flask caiga en el fallback local.

---

## 4. Auditoría del Fallback Criptográfico en Flask

Se auditaron exhaustivamente las rutas de ejecución en `VIGIA_API/ingest_service.py`:

### 4.1. Inspección de `generate_vigia_local_ca_bundle()`
Líneas 3486-3503 y 3612-3652:
```python
signer_client = None
if SignerClient is not None:
    try:
        client = SignerClient(certs_dir=base_dir)
        if client.ping():
            signer_client = client
    except Exception:
        signer_client = None

if ca_cert_p.is_file() and ca_key_p.is_file():
    ca_cert = x509.load_pem_x509_certificate(ca_cert_p.read_bytes())
    ca_key = serialization.load_pem_private_key(ca_key_p.read_bytes(), password=None)
elif ca_cert_p.is_file() and signer_client is not None:
    ca_cert = x509.load_pem_x509_certificate(ca_cert_p.read_bytes())
    ca_key = None
...
if signer_client is not None:
    # Emisión segura desacoplada vía IsolatedSigner
    sign_resp = signer_client.request_certificate(...)
else:
    # Emisión directa local (modo fallback / desarrollo)
    srv_cert = builder.sign(ca_key, hashes.SHA256())
```

**Análisis de Seguridad de Fallback:**
1. **Carga innecesaria de la clave:** Si `ca_key_p` existe en disco (situación real de producción), la primera rama `if ca_cert_p.is_file() and ca_key_p.is_file():` se cumple **incluso si `signer_client` está activo**. Flask carga `ca_key` en memoria en cada arranque.
2. **Fallback Silencioso (No Fail-Closed):** Si el demonio del firmador no ha sido iniciado, si la máquina se reinicia, si el pipe está ocupado o si la autenticación falla, `signer_client` se convierte en `None`. En lugar de lanzar una excepción fatal (`Fail-Closed`), el flujo continúa hacia `else:` y firma directamente en el proceso Flask con `ca_key`.
3. **Ausencia de Guard de Entorno:** No existe validación de variable de entorno (p. ej. `if os.environ.get("VIGIA_ENV") == "production": raise SignerUnavailableError(...)`). El fallback opera sin restricción en producción.

### 4.2. Inspección de `generate_vigia_crl()`
Líneas 3114-3150:
- Si `signer_client` no responde a `ping()`:
  ```python
  if not ca_cert_p.is_file() or not ca_key_p.is_file():
      raise FileNotFoundError(...)
  ca_cert = x509.load_pem_x509_certificate(ca_cert_p.read_bytes())
  ca_key = serialization.load_pem_private_key(ca_key_p.read_bytes(), password=None)
  crl = builder.sign(ca_key, hashes.SHA256())
  ```
- Exactamente el mismo comportamiento: ante la menor indisponibilidad del firmador, Flask lee `vigia_root_ca_key.pem` y firma la CRL localmente.

---

## 5. Auditoría de Políticas Criptográficas X.509

Se evaluó la lógica de validación de `VIGIA_Security/signer/policy.py` y `service.py`:

| Parámetro / Control | Evaluación Técnica | Estado |
| :--- | :--- | :--- |
| **Validación de Huella Root CA** | `service.py` valida `signed_cert.fingerprint(hashes.SHA256()) == AUTHORIZED_ROOT_CA_FINGERPRINT`. | **DEMOSTRADO** |
| **Firma a Profundidad 1 (Depth = 1)** | Certificados emitidos con `BasicConstraints(ca=False, path_length=None)`. | **DEMOSTRADO** |
| **Rechazo de Clave Débil** | Rechaza claves RSA < 2048 bits (`validate_public_key`). | **DEMOSTRADO** |
| **Rechazo de Extensiones CA en CSR** | Rechaza si CSR pide `BasicConstraints ca=True` o `KeyUsage keyCertSign`. | **DEMOSTRADO** |
| **Restricción EKU** | Exclusivamente `ExtendedKeyUsageOID.SERVER_AUTH`. | **DEMOSTRADO** |
| **Límite de Vigencia** | Máximo 90 días naturales estrictos. | **DEMOSTRADO** |
| **Filtrado de IPs Públicas y Multicast** | Rechaza `8.8.8.8`, `169.254.x.x`, `0.0.0.0` y multicast. | **DEMOSTRADO** |
| **Monotonicidad de CRL** | Secuencia monótona estricta garantizada en `sign_crl`. | **DEMOSTRADO** |
| **Manejo de IPv6 en SAN / CDP** | **Anomalía detectada:** `SignerPolicyValidator.validate_target_ip` acepta direcciones IPv6 loopback (`::1`) y ULA privadas (`fd00::1`). Al concatenar en URI de CDP (`f"http://{validated_ip}:{crl_port}/api/v1/tls/ca.crl"`), genera una URI inválida conforme a RFC 3986 (falta corchetes `[::1]`). | **PARCIAL** |
| **Atomicidad de Escritura** | Uso de archivos temporales `.tmp.<uuid>` y reemplazo atómico `os.replace`. | **DEMOSTRADO** |

---

## 6. Auditoría de Seguridad Operativa y Ciclo de Vida

1. **Arranque Automático y Recuperación:**
   - No existe servicio de Windows (`Get-Service`) ni tarea programada (`Get-ScheduledTask`) configurada para `IsolatedSigner`.
   - Si el sistema operativo se reinicia, el demonio **no arranca automáticamente**.
   - Ante la ausencia del demonio, Flask arranca sin advertencias y ejecuta el fallback local si la clave privada está presente.
2. **Persistencia del Rate Limit:**
   - La ventana deslizante de 5 firmas/minuto se almacena en `collections.deque` en la memoria volátil del proceso.
   - Si el demonio se reinicia (o se le fuerza a reiniciar mediante fallo intencional), el rate limit se reinicia inmediatamente a 0.
3. **Límites de Tamaño de Mensajes IPC:**
   - La capa IPC no impone límite de longitud sobre las cadenas PEM o serializaciones enviadas antes de deserializar.
4. **Protección del Log de Auditoría (`ca_issuance.jsonl`):**
   - El log se ubica en `certs/audit/`. Al ejecutarse bajo el mismo usuario `rog`, el proceso Flask tiene permisos para modificar, vaciar o eliminar los registros de auditoría de emisión.

---

## 7. Matriz de Evidencia de Controles

| ID | Control Evaluado | Evidencia Observada | Resultado | Nivel de Riesgo |
|---|---|---|---|---|
| **CTL-01** | Separación de Identidades en SO | Ambos procesos ejecutan bajo `laptop-h2lcul1v\rog`. Sin límites de seguridad de Windows entre ellos. | **FALLIDO** | **CRÍTICO** |
| **CTL-02** | Restricción NTFS sobre Root CA Key | `vigia_root_ca_key.pem` tiene permisos heredados `BUILTIN\Usuarios:(RX)` y `Usuarios autentificados:(M)`. | **FALLIDO** | **CRÍTICO** |
| **CTL-03** | Inaccesibilidad de Clave para Flask | `os.access('certs/vigia_root_ca_key.pem', os.R_OK)` es `True`. Flask puede abrir y leer la clave privada. | **FALLIDO** | **CRÍTICO** |
| **CTL-04** | Ausencia de Fallback en Producción | `generate_vigia_local_ca_bundle` y `generate_vigia_crl` contienen fallback directo a `ca_key` sin Fail-Closed. | **FALLIDO** | **CRÍTICO** |
| **CTL-05** | Descriptor de Seguridad en Pipe | Pipe creado con `lpSecurityAttributes=NULL`. Cualquier proceso de la sesión puede abrir handle. | **PARCIAL** | **MEDIO** |
| **CTL-06** | Autenticación Mutua IPC | HMAC-SHA256 implementado correctamente; token precompartido validado en handshake. | **DEMOSTRADO** | **BAJO** |
| **CTL-07** | Protección del Token IPC | Archivo `signer_ipc_auth.token` en `certs/` heredaría permisos de lectura para cualquier usuario autenticado. | **PARCIAL** | **ALTO** |
| **CTL-08** | Verificación de Identidad del Cliente | Se captura PID con `GetNamedPipeClientProcessId`, pero solo se registra en logs sin validación de ejecutable. | **PARCIAL** | **MEDIO** |
| **CTL-09** | Resiliencia y Concurrencia de Pipe | Monohilo, `nMaxInstances=1`, sin timeout en `recv()`. Bloqueo completo demostrado ante cliente silencioso. | **FALLIDO** | **ALTO** |
| **CTL-10** | Validación de Huella SHA-256 CA | Coincidencia estricta contra `E593B2D0B808BD8F8E97582ECDEBEAD29AEBC0F9F4BA9EF6ADB2D8E4362E4F4D`. | **DEMOSTRADO** | **BAJO** |
| **CTL-11** | Política de Emisión X.509 (Prof. 1) | Emite hoja `ca=False`, `pathlen=None`, `serverAuth`, RSA $\ge$ 2048 bits, máx 90 días. | **DEMOSTRADO** | **BAJO** |
| **CTL-12** | Filtrado de SANs | Filtra IPs públicas, loopback, APIPA y multicast. Brecha menor: admite IPv6 privada sin corchetes en CDP. | **PARCIAL** | **BAJO** |
| **CTL-13** | Rate Limiting de Firma | 5 firmas/minuto aplicado correctamente en memoria. No sobrevive a reinicios del proceso. | **PARCIAL** | **MEDIO** |
| **CTL-14** | Atomicidad de Escritura | Reemplazo transaccional mediante `os.replace` verificado en certificados, CRL y manifest. | **DEMOSTRADO** | **BAJO** |
| **CTL-15** | Recuperación ante Reinicio del SO | No existe servicio Windows ni tarea programada. Sin persistencia de inicio automático. | **NO DEMOSTRADO** | **ALTO** |

---

## 8. Vulnerabilidades y Riesgos Residuales Identificados

1. **VULN-01 (Crítica — Falsa Sensación de Aislamiento):**  
   Aunque el código del firmador desacoplado existe, en el sistema de archivos real la clave privada `vigia_root_ca_key.pem` está expuesta para lectura y escritura directa por el proceso Flask.
2. **VULN-02 (Crítica — Fallback Automático Inseguro):**  
   Si el firmador se detiene, Flask continúa emitiendo certificados y CRLs cargando la clave raíz en memoria sin emitir error `Fail-Closed`.
3. **VULN-03 (Alta — Denegación de Servicio por Pipe Monohilo):**  
   Cualquier conexión local al pipe que no envíe datos congela el servidor IPC, forzando a Flask a caer inmediatamente en la firma local.
4. **VULN-04 (Media — Token Accesible por Misma Identidad):**  
   Al correr bajo el mismo usuario interactivo, cualquier proceso de usuario puede leer `signer_ipc_auth.token` y firmar certificados arbitrarios dentro de los rangos de la política.

---

## 9. Recomendaciones de Remediación (No Implementadas)

*De acuerdo con las restricciones de la auditoría, no se han aplicado modificaciones. Se documentan exclusivamente como guía de diseño para fases posteriores:*

1. **Eliminar el Fallback Local en Producción:**  
   En `ingest_service.py`, si `signer_client` no responde, la función debe abortar con excepción `SignerUnavailableError` de inmediato. La rama `else:` debe existir únicamente si una variable explícita `VIGIA_DEV_ALLOW_LOCAL_SIGNING=true` está configurada, prohibiéndola en producción.
2. **Remover `vigia_root_ca_key.pem` del Alcance de Flask:**  
   La clave privada `vigia_root_ca_key.pem` debe reubicarse a un directorio exclusivo del firmador (p. ej. `certs/signer_private/`) al cual el usuario de Flask no tenga permiso de lectura, o eliminarse de la máquina host si el firmador reside en un contenedor/servicio aislado.
3. **Cuenta de Servicio Windows Dedicada:**  
   Crear un usuario de servicio local (ej. `vigia_signer_svc` o `NT SERVICE\VigiaSigner`) para ejecutar el demonio. Configurar las ACLs NTFS para que **únicamente** esa cuenta y `SYSTEM` tengan lectura sobre la clave privada.
4. **Timeout y Concurrencia en Named Pipe:**  
   Implementar un timeout de conexión y lectura en el Named Pipe, o migrar la aceptación de conexiones a hilos independientes (`ThreadedPipeListener`) para evitar bloqueos por clientes lentos.
5. **Servicio Windows de Recuperación:**  
   Empaquetar `VIGIA_Security.signer.daemon` como un Servicio de Windows gestionado con recuperación automática ante caídas (`sc.exe create VigiaSigner ...`).
6. **Corrección de Formato IPv6:**  
   Rechazar explícitamente direcciones IPv6 en `SignerPolicyValidator` si la solución es estrictamente IPv4 LAN, o formatear correctamente las URIs de CDP con corchetes `[<ipv6>]`.
