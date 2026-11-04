<#
.SYNOPSIS
    Diagnostico Pasivo de Red LAN, Perfil de Windows, Firewall y Servidor VIGIA (VIGIA-NET-02).
.DESCRIPTION
    Realiza una inspeccion 100% no invasiva del estado de conectividad LAN:
    - Interfaces fisicas activas, IPs privadas RFC 1918 y adaptadores virtuales filtrados.
    - Perfil de red activo en Windows (Public / Private) para la interfaz LAN.
    - Estado de escucha del socket TCP del backend (proceso, PID, enlace).
    - Reglas de firewall existentes, alcance de perfil y evaluacion de efectividad.
    - Clasificacion rigurosa en categorias [OK], [ADVERTENCIA], [ERROR] y [NO VERIFICABLE].
    ESTRICTAMENTE PASIVO: No modifica firewall, perfiles de red, certificados ni servicios.
#>

[CmdletBinding()]
param(
    [switch]$Json
)

$ErrorActionPreference = "Continue"

# 1. Resolver rutas deterministas
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$repoRoot = Resolve-Path (Join-Path $scriptDir "..")
$softwareRoot = Resolve-Path (Join-Path $repoRoot "..")
$envFile = Join-Path $softwareRoot ".env"

$py = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $py)) {
    Write-Error "No se encontro el interprete Python en '$py'. Active el entorno virtual."
    exit 1
}

# 2. Leer configuracion declarativa de Software/.env (sin secretos)
$configuredPort = 5000
$configuredHost = "0.0.0.0"
$tlsEnabled = $false

if (Test-Path -LiteralPath $envFile) {
    Get-Content -Path $envFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#")) {
            $parts = $line.Split("=", 2)
            if ($parts.Count -eq 2) {
                $k = $parts[0].Trim()
                $v = $parts[1].Trim().Trim("'").Trim('"')
                if ($k -eq "VIGIA_DEV_PORT" -and $v) { $configuredPort = [int]$v }
                if ($k -eq "VIGIA_DEV_HOST" -and $v) { $configuredHost = $v }
                if ($k -eq "VIGIA_ENABLE_TLS" -and $v -in @("1", "true", "yes", "on")) { $tlsEnabled = $true }
            }
        }
    }
}

# 3. Ejecutar diagnostico de bajo nivel en VIGIA_Core.network
$env:PYTHONPATH = $repoRoot.Path
$rawJson = & $py -m VIGIA_Core.network --port $configuredPort --json 2>$null
if ($LASTEXITCODE -ne 0 -or -not $rawJson) {
    Write-Error "Fallo al ejecutar 'VIGIA_Core.network': no se pudo recopilar telemetria de red."
    exit 1
}

$coreReport = $rawJson | ConvertFrom-Json

# 4. Consultar perfil de red de Windows (Get-NetConnectionProfile)
$netProfiles = @()
try {
    $netProfiles = Get-NetConnectionProfile -ErrorAction SilentlyContinue
} catch {
    $netProfiles = @()
}

$recCandidate = $coreReport.recommended_candidate
$matchedProfile = $null
if ($recCandidate -and $netProfiles) {
    $matchedProfile = $netProfiles | Where-Object {
        $_.InterfaceAlias -eq $recCandidate.interface -or $_.Name -eq $recCandidate.interface
    } | Select-Object -First 1

    if (-not $matchedProfile) {
        $matchedProfile = $netProfiles | Where-Object { $_.IPv4Connectivity -eq "Internet" } | Select-Object -First 1
    }
}

$activeCategory = if ($matchedProfile) { $matchedProfile.NetworkCategory.ToString() } else { "No detectado" }

# 5. Consultar estado del socket local y proceso (Get-NetTCPConnection)
$tcpConns = @()
try {
    $tcpConns = @(Get-NetTCPConnection -LocalPort $configuredPort -ErrorAction SilentlyContinue)
} catch {
    $tcpConns = @()
}

$isListening = $false
$owningPid = $null
$processName = "Inactivo"
$boundAddress = "N/A"

if ($tcpConns -and $tcpConns.Count -gt 0) {
    $listenConn = $tcpConns | Where-Object { $_.State -eq "Listen" -or $_.State -eq 2 } | Select-Object -First 1
    if (-not $listenConn) {
        $activeConn = $tcpConns | Where-Object { $_.OwningProcess -gt 0 } | Select-Object -First 1
        if ($activeConn) { $listenConn = $activeConn }
    }
    if ($listenConn) {
        $isListening = $true
        $owningPid = $listenConn.OwningProcess
        $boundAddress = $listenConn.LocalAddress
        try {
            $proc = Get-Process -Id $owningPid -ErrorAction SilentlyContinue
            if ($proc) { $processName = $proc.ProcessName }
        } catch {
            $processName = "Desconocido (PID $owningPid)"
        }
    }
}

# Fallback si Get-NetTCPConnection no detecto listener pero el socket esta activo
if (-not $isListening -and $diagReport.socket_probe.is_active) {
    $isListening = $true
    $boundAddress = "127.0.0.1"
    try {
        $netstatLine = netstat -ano | Select-String ":$configuredPort\s" | Select-Object -First 1
        if ($netstatLine -match '\s+(\d+)\s*$') {
            $owningPid = [int]$matches[1]
            $proc = Get-Process -Id $owningPid -ErrorAction SilentlyContinue
            if ($proc) { $processName = $proc.ProcessName }
        }
    } catch {}
}

# Probar endpoint HTTP/HTTPS si esta escuchando
$endpointStatus = "No verificado (Servidor no escuchando)"
if ($isListening) {
    $scheme = if ($tlsEnabled) { "https" } else { "http" }
    $testUrl = "${scheme}://127.0.0.1:${configuredPort}/api/v1/system/network"
    try {
        $curlRes = & curl.exe -k -s -I -m 2 $testUrl 2>$null
        if ($curlRes -match "200 OK") {
            $endpointStatus = "200 OK ($testUrl responde)"
        } elseif ($curlRes -match "HTTP") {
            $statusLine = ($curlRes -split "`n")[0].Trim()
            $endpointStatus = "Respondio: $statusLine"
        } else {
            $endpointStatus = "Socket responde, pero no devolvio HTTP 200"
        }
    } catch {
        $endpointStatus = "Error al sondear endpoint: $_"
    }
}

# 6. Consultar reglas del Firewall de Windows (Get-NetFirewallRule & netsh)
$firewallRules = @()
try {
    $rawRules = Get-NetFirewallRule -ErrorAction SilentlyContinue | Where-Object {
        $_.DisplayName -match "5000" -or $_.DisplayName -match "VIGIA" -or $_.Name -match "5000" -or $_.Name -match "VIGIA"
    }
    if ($rawRules) {
        foreach ($r in $rawRules) {
            $firewallRules += [PSCustomObject]@{
                Name        = $r.Name
                DisplayName = $r.DisplayName
                Enabled     = $r.Enabled
                Direction   = $r.Direction.ToString()
                Action      = $r.Action.ToString()
                Profile     = $r.Profile.ToString()
                Source      = "Get-NetFirewallRule"
            }
        }
    }
} catch {
    # Fallback si Get-NetFirewallRule requiere elevacion
}

# Evaluar efectividad de la regla
$firewallEffective = $false
$firewallReason = ""

if ($firewallRules.Count -eq 0) {
    $firewallReason = "No existe ninguna regla de entrada registrada para el puerto TCP $configuredPort o VIGIA."
} else {
    $inboundRules = $firewallRules | Where-Object { $_.Direction -eq "Inbound" -and $_.Action -eq "Allow" }
    if ($inboundRules.Count -eq 0) {
        $firewallReason = "Existen reglas relacionadas, pero ninguna es de entrada (Inbound) con accion 'Allow'."
    } else {
        $activeInbound = $inboundRules | Where-Object { $_.Enabled -eq $true }
        if ($activeInbound.Count -eq 0) {
            $firewallReason = "Existe regla de entrada pero esta DESHABILITADA."
        } else {
            $matchingProfileRule = $activeInbound | Where-Object {
                $_.Profile -eq "Any" -or $_.Profile -split "," -contains $activeCategory
            }
            if ($matchingProfileRule) {
                $firewallEffective = $true
                $firewallReason = "Existe regla habilitada que aplica al perfil activo ('$activeCategory')."
            } else {
                $ruleProfiles = ($activeInbound | ForEach-Object { $_.Profile }) -join ", "
                $firewallReason = "Existen reglas para perfiles [$ruleProfiles], pero NO aplican al perfil activo ('$activeCategory')."
            }
        }
    }
}

# 7. Diagnostico y Clasificacion por Seccion
$statusInterfaces = if ($coreReport.candidates.Count -gt 0) { "OK" } else { "ERROR" }
$statusProfile = if ($activeCategory -eq "Private") { "OK" } elseif ($activeCategory -eq "Public") { "ADVERTENCIA" } else { "NO VERIFICABLE" }
$statusServer = if ($isListening) { "OK" } else { "ADVERTENCIA" }
$statusFirewall = if ($firewallEffective) { "OK" } else { "ADVERTENCIA" }
$statusInterClient = "NO VERIFICABLE"

# Si se solicito JSON, emitir objeto estructurado completo
if ($Json) {
    [PSCustomObject]@{
        timestamp               = (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ")
        status_summary          = @{
            interfaces_status   = $statusInterfaces
            profile_status      = $statusProfile
            server_status       = $statusServer
            firewall_status     = $statusFirewall
            inter_client_status = $statusInterClient
        }
        lan_interfaces          = $coreReport.candidates
        filtered_interfaces     = $coreReport.filtered_virtual
        recommended_ip          = if ($recCandidate) { $recCandidate.ip } else { $null }
        recommended_interface   = if ($recCandidate) { $recCandidate.interface } else { $null }
        default_route_ip        = $coreReport.default_route_ip
        network_category        = $activeCategory
        matched_profile_name    = if ($matchedProfile) { $matchedProfile.Name } else { $null }
        server                  = @{
            configured_port     = $configuredPort
            configured_host     = $configuredHost
            is_listening        = $isListening
            bound_address       = $boundAddress
            owning_pid          = $owningPid
            process_name        = $processName
            endpoint_status     = $endpointStatus
            tls_enabled         = $tlsEnabled
        }
        firewall                = @{
            effective_rule      = $firewallEffective
            reason              = $firewallReason
            rules_found         = $firewallRules
        }
        access_urls             = $coreReport.access_urls
    } | ConvertTo-Json -Depth 5
    exit 0
}

# Salida formateada legible en consola
Write-Host ""
Write-Host ("=" * 72) -ForegroundColor Cyan
Write-Host " VIGIA Vision Systems - Diagnostico Pasivo de Red LAN (VIGIA-NET-02)" -ForegroundColor Cyan
Write-Host ("=" * 72) -ForegroundColor Cyan

# SECCION A: INTERFACES DE RED
Write-Host ""
Write-Host "A. INTERFACES DE RED FISICAS Y LAN:" -ForegroundColor Yellow
if ($coreReport.candidates.Count -gt 0) {
    foreach ($c in $coreReport.candidates) {
        $recMark = if ($c.is_recommended) { " [RECOMENDADA]" } else { "" }
        Write-Host "   [$statusInterfaces] $($c.interface): $($c.ip)$recMark" -ForegroundColor Green
    }
} else {
    Write-Host "   [ERROR] No se detecto ninguna interfaz fisica con direccion IPv4 privada utilizable." -ForegroundColor Red
}

if ($coreReport.default_route_ip) {
    Write-Host "   -> Ruta externa del kernel: $($coreReport.default_route_ip)" -ForegroundColor Gray
}

# Interfaces virtuales / excluidas
if ($coreReport.filtered_virtual.Count -gt 0) {
    Write-Host "`n   Adaptadores virtuales o inactivos filtrados:" -ForegroundColor Gray
    foreach ($f in $coreReport.filtered_virtual) {
        Write-Host "     * $($f.interface) ($($f.ip)): $($f.filter_reason)" -ForegroundColor DarkGray
    }
}

# SECCION B: PERFIL DE RED DE WINDOWS
Write-Host ""
Write-Host "B. PERFIL DE RED DE WINDOWS:" -ForegroundColor Yellow
if ($matchedProfile) {
    $profColor = if ($activeCategory -eq "Private") { "Green" } else { "Yellow" }
    Write-Host "   [$statusProfile] Interfaz '$($matchedProfile.InterfaceAlias)' en red '$($matchedProfile.Name)'" -ForegroundColor $profColor
    Write-Host "        Categoria de perfil: $activeCategory" -ForegroundColor $profColor
    if ($activeCategory -eq "Public") {
        Write-Host "        [!] ADVERTENCIA: La red esta catalogada como 'Public'." -ForegroundColor Yellow
        Write-Host "            Windows Defender Firewall descarta por omision conexiones entrantes (SYN)" -ForegroundColor Yellow
        Write-Host "            desde otros dispositivos de la LAN, provocando ERR_TIMED_OUT en celulares." -ForegroundColor Yellow
        Write-Host "            (No se altera el perfil automaticamente por seguridad; configure a 'Privada'" -ForegroundColor Gray
        Write-Host "            en Ajustes de Windows si es su red local de confianza)." -ForegroundColor Gray
    }
} else {
    Write-Host "   [NO VERIFICABLE] No se pudo correlacionar la interfaz fisica con un perfil de red de Windows." -ForegroundColor DarkYellow
}

# SECCION C: SERVIDOR VIGIA
Write-Host ""
Write-Host "C. ESTADO DEL SERVIDOR VIGIA:" -ForegroundColor Yellow
Write-Host "   - Puerto configurado: TCP $configuredPort (Host enlace: $configuredHost)" -ForegroundColor Gray
Write-Host "   - Esquema de transporte: $(if ($tlsEnabled) { 'HTTPS (TLS Activo)' } else { 'HTTP (Texto plano)' })" -ForegroundColor Gray

if ($isListening) {
    Write-Host "   [OK] Socket escuchando en ${boundAddress}:${configuredPort} (PID: $owningPid, Proceso: $processName)" -ForegroundColor Green
    Write-Host "        Sondeo local 127.0.0.1: Conexión TCP exitosa" -ForegroundColor Green
    Write-Host "        Endpoint de diagnostico: $endpointStatus" -ForegroundColor $(if ($endpointStatus -match "200 OK") { "Green" } else { "Yellow" })
} else {
    Write-Host "   [ADVERTENCIA] No hay ningun proceso escuchando en el puerto TCP $configuredPort." -ForegroundColor Yellow
    Write-Host "                 El servidor esta detenido. Ejecute '.\vigia.ps1 api' para iniciarlo." -ForegroundColor Gray
}

# URLs de acceso calculadas
Write-Host "   - URLs calculadas:" -ForegroundColor Gray
Write-Host "       Local:        $($coreReport.access_urls.local_url)" -ForegroundColor Gray
Write-Host "       LAN:          $($coreReport.access_urls.recommended_lan_url)" -ForegroundColor Gray
Write-Host "       Enrolamiento: $($coreReport.access_urls.effective_qr_base_url)" -ForegroundColor Gray

# SECCION D: FIREWALL DE WINDOWS
Write-Host ""
Write-Host "D. REGLAS DE FIREWALL DE WINDOWS:" -ForegroundColor Yellow
if ($firewallEffective) {
    Write-Host "   [OK] $firewallReason" -ForegroundColor Green
} else {
    Write-Host "   [ADVERTENCIA] $firewallReason" -ForegroundColor Yellow
    Write-Host "                 Sin una regla entrante efectiva, las peticiones externas al puerto $configuredPort" -ForegroundColor Gray
    Write-Host "                 pueden ser descartadas silenciosamente (ERR_TIMED_OUT)." -ForegroundColor Gray
}

if ($firewallRules.Count -gt 0) {
    Write-Host "`n   Reglas registradas en el sistema:" -ForegroundColor Gray
    foreach ($r in $firewallRules) {
        $rColor = if ($r.Enabled -and $r.Direction -eq "Inbound") { "Green" } else { "DarkGray" }
        Write-Host "     * $($r.DisplayName) [Perfil: $($r.Profile), Dir: $($r.Direction), Habilitada: $($r.Enabled)]" -ForegroundColor $rColor
    }
}

# SECCION E: DIAGNOSTICO FINAL Y CLASIFICACION
Write-Host ""
Write-Host ("-" * 72) -ForegroundColor Cyan
Write-Host "E. RESUMEN Y CLASIFICACION DE CONECTIVIDAD:" -ForegroundColor Cyan
Write-Host ("-" * 72) -ForegroundColor Cyan

function Print-Summary([string]$Label, [string]$Status, [string]$Detail) {
    $color = switch ($Status) {
        "OK"             { "Green" }
        "ADVERTENCIA"    { "Yellow" }
        "ERROR"          { "Red" }
        "NO VERIFICABLE" { "DarkYellow" }
        default          { "White" }
    }
    Write-Host ("   {0,-38} : [{1}] {2}" -f $Label, $Status, $Detail) -ForegroundColor $color
}

$candIpStr = if ($recCandidate) { $recCandidate.ip } else { "Ninguna" }
$servDetailStr = if ($isListening) { "Escuchando en $boundAddress (PID $owningPid)" } else { "Detenido" }

Print-Summary -Label "1. Interfaces LAN fisicas" -Status $statusInterfaces -Detail "IP: $candIpStr"
Print-Summary -Label "2. Perfil de Red de Windows" -Status $statusProfile -Detail "Perfil: $activeCategory"
Print-Summary -Label "3. Servidor VIGIA (Puerto $configuredPort)" -Status $statusServer -Detail $servDetailStr
Print-Summary -Label "4. Reglas de Firewall (Puerto $configuredPort)" -Status $statusFirewall -Detail $firewallReason
Print-Summary -Label "5. Conectividad Inter-Clientes Wi-Fi" -Status $statusInterClient -Detail "Requiere prueba activa desde dispositivo externo (AP Isolation)"

Write-Host ""
Write-Host "NOTAS DE SEGURIDAD Y DIAGNOSTICO:" -ForegroundColor Gray
Write-Host "- Este diagnostico es estrictamente pasivo; ninguna regla ni configuracion fue alterada." -ForegroundColor Gray
Write-Host "- No se puede culpar de forma concluyente al Firewall o al Router sin una prueba externa." -ForegroundColor Gray
Write-Host "- Para probar el flujo completo: inicie el servidor con '.\vigia.ps1 api' y revise la conectividad." -ForegroundColor Gray
Write-Host ("=" * 72) -ForegroundColor Cyan
Write-Host ""
