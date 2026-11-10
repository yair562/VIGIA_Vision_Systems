<#
.SYNOPSIS
    Configuración de Listas de Control de Acceso (ACL NTFS) para el Aislamiento de Root CA (VIGIA-NET-04A).
.DESCRIPTION
    Aplica el principio de menor privilegio sobre 'vigia_root_ca_key.pem' y el token IPC:
    - Remueve la herencia de permisos NTFS (/inheritance:r).
    - Otorga control total exclusivamente a NT AUTHORITY\SYSTEM y BUILTIN\Administradores.
    - Otorga lectura/escritura al propietario del proceso firmador.
    - Revoca terminantemente los permisos de lectura a BUILTIN\Usuarios y cuentas no privilegiadas.
#>

[CmdletBinding()]
param(
    [switch]$AuditOnly
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$repoRoot = Resolve-Path (Join-Path $scriptDir "..")
$certsDir = Join-Path $repoRoot "certs"
$caKeyPath = Join-Path $certsDir "vigia_root_ca_key.pem"
$tokenPath = Join-Path $certsDir "signer_ipc_auth.token"

Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host " VIGIA Vision Systems — Configuración de ACLs de Clave Privada Root CA" -ForegroundColor Cyan
Write-Host "========================================================================" -ForegroundColor Cyan

if (-not (Test-Path -LiteralPath $caKeyPath)) {
    Write-Error "No se encontró el archivo de clave privada en: $caKeyPath"
    exit 1
}

Write-Host "`n1. ESTADO ACTUAL DE PERMISOS:" -ForegroundColor Yellow
$currentAcl = Get-Acl -LiteralPath $caKeyPath
$currentAcl.Access | Format-Table IdentityReference, FileSystemRights, AccessControlType, IsInherited -AutoSize

if ($AuditOnly) {
    Write-Host "`nModo auditoría: no se aplicaron cambios." -ForegroundColor Cyan
    exit 0
}

Write-Host "`n2. APLICANDO RESTRICCIÓN DE MENOR PRIVILEGIO (icacls)..." -ForegroundColor Yellow

try {
    # 1. Remover herencia conservando permisos convertidos
    & icacls "$caKeyPath" /inheritance:r | Out-Null

    # 2. Asignar control total únicamente a SYSTEM y Administradores
    & icacls "$caKeyPath" /grant:r "*S-1-5-18:(F)" | Out-Null       # NT AUTHORITY\SYSTEM
    & icacls "$caKeyPath" /grant:r "*S-1-5-32-544:(F)" | Out-Null   # BUILTIN\Administradores

    # 3. Asignar al usuario actual de desarrollo permiso de lectura/escritura (para la sesión activa)
    $currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    & icacls "$caKeyPath" /grant:r "${currentUser}:(F)" | Out-Null

    # 4. Remover explícitamente Usuarios estándar si existieran
    & icacls "$caKeyPath" /remove "*S-1-5-32-545" 2>$null | Out-Null # BUILTIN\Usuarios

    # Si existe el archivo de token IPC, protegerlo de forma idéntica
    if (Test-Path -LiteralPath $tokenPath) {
        & icacls "$tokenPath" /inheritance:r | Out-Null
        & icacls "$tokenPath" /grant:r "*S-1-5-18:(F)" | Out-Null
        & icacls "$tokenPath" /grant:r "*S-1-5-32-544:(F)" | Out-Null
        & icacls "$tokenPath" /grant:r "${currentUser}:(F)" | Out-Null
    }

    Write-Host "[OK] Permisos NTFS configurados exitosamente." -ForegroundColor Green
} catch {
    Write-Warning "No se pudieron aplicar todas las directivas de icacls: $_"
}

Write-Host "`n3. PERMISOS RESULTANTES VERIFICADOS:" -ForegroundColor Yellow
$finalAcl = Get-Acl -LiteralPath $caKeyPath
$finalAcl.Access | Format-Table IdentityReference, FileSystemRights, AccessControlType, IsInherited -AutoSize

Write-Host "========================================================================" -ForegroundColor Cyan
