<#
.SYNOPSIS
    Aprovisionamiento, Verificacion y Reversion Segura de Confianza TLS para VIGIA (VIGIA-TLS-02B-R2).
.DESCRIPTION
    Gestiona el ciclo de vida de confianza del certificado publico Root CA de VIGIA
    exclusivamente en el almacen de certificados del usuario actual:
    Cert:\CurrentUser\Root (Trusted Root Certification Authorities).

    Acciones soportadas:
    - verify  : Auditoria pasiva sin modificaciones (comprueba presencia y huella SHA-256).
    - trust   : Instalacion interactiva previa validacion criptografica estricta e idempotente.
    - untrust : Reversion/desinstalacion segura identificando exclusivamente la huella SHA-256 autorizada.

    Principios de Seguridad y Alcance:
    - No requiere elevacion / privilegios de Administrador.
    - No modifica LocalMachine\Root ni politicas de seguridad globales de Windows.
    - Valida de forma ineludible la huella SHA-256 autorizada antes de cualquier accion.
    - La huella autorizada NUNCA se omite, independientemente de cualquier parametro.
    - La confirmacion interactiva es obligatoria en operaciones reales sobre Cert:\CurrentUser\Root.
    - Los parametros -Force y -Json NUNCA omiten la confirmacion interactiva en el almacen real.
    - VIGIA_ALLOW_IN_MEMORY solo habilita bypass en pruebas con almacenes mockeados fuera del sistema.
    - No utiliza coincidencias de Subject, FriendlyName o CN; solo huella exacta SHA-256.
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Position=0)]
    [ValidateSet('trust', 'verify', 'status', 'untrust', 'remove')]
    [string]$Action = 'verify',

    [string]$CertPath = "",
    [string]$ExpectedThumbprint = "E593B2D0B808BD8F8E97582ECDEBEAD29AEBC0F9F4BA9EF6ADB2D8E4362E4F4D",
    [string]$StorePath = "Cert:\CurrentUser\Root",
    [switch]$Force,
    [switch]$Json
)

$ErrorActionPreference = "Stop"

function Get-CertSha256($Certificate) {
    if ($Certificate -is [System.IO.FileInfo]) {
        try {
            $Certificate = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($Certificate.FullName)
        } catch {
            return ""
        }
    }
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    $hashBytes = $hasher.ComputeHash($Certificate.RawData)
    return (($hashBytes | ForEach-Object { $_.ToString("X2") }) -join "").ToUpperInvariant()
}

# 1. Prohibir estrictamente cualquier operacion sobre LocalMachine
if ($StorePath -like "*LocalMachine*") {
    $errMsg = "OPERACION DENEGADA: VIGIA prohibe estrictamente modificar almacenes en LocalMachine. Solo se autoriza CurrentUser."
    if ($Json) {
        [PSCustomObject]@{
            status = "FORBIDDEN_STORE"
            action = $Action
            store_path = $StorePath
            error = $errMsg
        } | ConvertTo-Json -Depth 4
    } else {
        Write-Error $errMsg
    }
    exit 1
}

# 2. Resolver ruta determinista de la Root CA
if (-not $CertPath) {
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
    $repoRoot = Resolve-Path (Join-Path $scriptDir "..")
    $CertPath = Join-Path $repoRoot.Path "certs\vigia_root_ca.crt"
} else {
    $CertPath = [System.IO.Path]::GetFullPath($CertPath)
}

$expectedFpClean = $ExpectedThumbprint.Replace(":", "").Replace(" ", "").Trim().ToUpperInvariant()

# 3. Comprobar existencia del archivo de certificado
if (-not (Test-Path -LiteralPath $CertPath)) {
    $errMsg = "No se encontro el archivo de Root CA en '$CertPath'."
    if ($Json) {
        [PSCustomObject]@{
            status = "ERROR"
            action = $Action
            file_exists = $false
            cert_path = $CertPath
            error = $errMsg
        } | ConvertTo-Json -Depth 4
        exit 1
    } else {
        Write-Error $errMsg
        exit 1
    }
}

# 4. Cargar certificado y calcular huella SHA-256
try {
    $cert = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($CertPath)
} catch {
    $errMsg = "Fallo al analizar el certificado X.509 en '$CertPath': $_"
    if ($Json) {
        [PSCustomObject]@{
            status = "ERROR"
            action = $Action
            file_exists = $true
            cert_path = $CertPath
            error = $errMsg
        } | ConvertTo-Json -Depth 4
        exit 1
    } else {
        Write-Error $errMsg
        exit 1
    }
}

$actualFp = Get-CertSha256 -Certificate $cert

# 5. Validar huella contra la autorizada (Ineludible - Nunca se omite)
$fingerprintMatches = ($actualFp -eq $expectedFpClean)
if (-not $fingerprintMatches) {
    $errMsg = "DISCREPANCIA CRIPTOGRAFICA: La huella SHA-256 del certificado ($actualFp) no coincide con la esperada ($expectedFpClean). Operacion cancelada."
    if ($Json) {
        [PSCustomObject]@{
            status = "FINGERPRINT_MISMATCH"
            action = $Action
            cert_path = $CertPath
            actual_fingerprint = $actualFp
            expected_fingerprint = $expectedFpClean
            error = $errMsg
        } | ConvertTo-Json -Depth 4
        exit 1
    } else {
        Write-Error $errMsg
        exit 1
    }
}

# 6. Inspeccionar el almacen especificado buscando coincidencia estricta de SHA-256
$isInstalled = $false
$matchingStoreCert = $null
if (Test-Path -LiteralPath $StorePath) {
    $storeCerts = Get-ChildItem -Path $StorePath -ErrorAction SilentlyContinue
    foreach ($sc in $storeCerts) {
        try {
            $scFp = Get-CertSha256 -Certificate $sc
            if ($scFp -eq $actualFp) {
                $isInstalled = $true
                $matchingStoreCert = $sc
                break
            }
        } catch {
            # Continuar inspeccion si un cert individual falla al leerse
        }
    }
} else {
    if (-not $Json) {
        Write-Warning "El almacen '$StorePath' no existe o no es accesible."
    }
}

# 7. Normalizar identificacion del almacen real del sistema
$normalizedStore = $StorePath.TrimEnd('\/').ToLowerInvariant()
$isRealStore = ($normalizedStore -eq "cert:\currentuser\root")
# VIGIA_ALLOW_IN_MEMORY solo habilita bypass en pruebas con almacenes mockeados FUERA del sistema
$isTestIsolated = ($env:VIGIA_ALLOW_IN_MEMORY -eq "1" -and -not $isRealStore)

# ----------------------------------------------------------------------
# ACCION: VERIFY o STATUS (Auditoria Pasiva)
# ----------------------------------------------------------------------
if ($Action -in @('verify', 'status')) {
    if ($Json) {
        [PSCustomObject]@{
            status = if ($isInstalled) { "INSTALLED" } else { "NOT_INSTALLED" }
            action = "verify"
            cert_path = $CertPath
            subject = $cert.Subject
            issuer = $cert.Issuer
            serial_number = $cert.SerialNumber
            not_before = $cert.NotBefore.ToString("o")
            not_after = $cert.NotAfter.ToString("o")
            sha256_fingerprint = $actualFp
            fingerprint_matches = $fingerprintMatches
            store_path = $StorePath
            is_installed = $isInstalled
        } | ConvertTo-Json -Depth 4
    } else {
        Write-Host "========================================================================" -ForegroundColor Cyan
        Write-Host " VIGIA Vision Systems - Verificacion de Confianza Root CA (TLS-02B)" -ForegroundColor Cyan
        Write-Host "========================================================================" -ForegroundColor Cyan
        Write-Host "Archivo certificado : $CertPath"
        Write-Host "Sujeto              : $($cert.Subject)"
        Write-Host "Emisor              : $($cert.Issuer)"
        Write-Host "Numero de Serie     : $($cert.SerialNumber)"
        Write-Host "Validez             : Desde $($cert.NotBefore.ToString('yyyy-MM-dd HH:mm:ss')) Hasta $($cert.NotAfter.ToString('yyyy-MM-dd HH:mm:ss'))"
        Write-Host "Huella SHA-256      : $actualFp"
        Write-Host "Coincidencia Huella : [OK] Coincide exactamente con la huella autorizada" -ForegroundColor Green
        Write-Host "Almacen objetivo    : $StorePath"
        if ($isInstalled) {
            Write-Host "Estado en Almacen   : [OK] INSTALADO Y CONFIABLE" -ForegroundColor Green
            Write-Host "`nWindows y los navegadores del usuario confian en la Root CA de VIGIA." -ForegroundColor Green
        } else {
            Write-Host "Estado en Almacen   : [ADVERTENCIA] NO INSTALADO" -ForegroundColor Yellow
            Write-Host "`nPara instalar la Root CA en su almacen de usuario y evitar advertencias:"
            Write-Host "  .\\vigia.ps1 trust-ca`n" -ForegroundColor Yellow
        }
        Write-Host "========================================================================" -ForegroundColor Cyan
    }
    exit 0
}

# ----------------------------------------------------------------------
# ACCION: TRUST (Instalacion de Confianza)
# ----------------------------------------------------------------------
if ($Action -eq 'trust') {
    if ($isInstalled) {
        if ($Json) {
            [PSCustomObject]@{
                status = "ALREADY_INSTALLED"
                action = "trust"
                cert_path = $CertPath
                store_path = $StorePath
                sha256_fingerprint = $actualFp
                message = "El certificado ya se encuentra instalado en el almacen de destino."
            } | ConvertTo-Json -Depth 4
        } else {
            Write-Host "`n[INFO] El certificado Root CA de VIGIA ya esta instalado en '$StorePath'." -ForegroundColor Green
            Write-Host "Huella SHA-256 verificada: $actualFp"
            Write-Host "No se requieren acciones adicionales (operacion idempotente).`n"
        }
        exit 0
    }

    # Mostrar informacion antes de confirmacion interactiva
    if (-not $Json) {
        Write-Host "========================================================================" -ForegroundColor Yellow
        Write-Host " VIGIA Vision Systems - Instalacion de Confianza Root CA (TLS-02B)" -ForegroundColor Yellow
        Write-Host "========================================================================" -ForegroundColor Yellow
        Write-Host "Se aprovisionara la siguiente Autoridad Certificadora privada:"
        Write-Host "  Archivo      : $CertPath"
        Write-Host "  Sujeto       : $($cert.Subject)"
        Write-Host "  Emisor       : $($cert.Issuer)"
        Write-Host "  Numero Serie : $($cert.SerialNumber)"
        Write-Host "  Validez      : Hasta $($cert.NotAfter.ToString('yyyy-MM-dd HH:mm:ss'))"
        Write-Host "  Huella SHA256: $actualFp"
        Write-Host "  Destino      : $StorePath (Exclusivo Usuario Actual, Sin privilegios Admin)"
        Write-Host "------------------------------------------------------------------------"
    }

    # Confirmacion interactiva obligatoria en el almacen real
    if (-not $isTestIsolated) {
        if (-not $Json) {
            if ($Force) {
                Write-Host "`n[AVISO DE SEGURIDAD] Por directriz criptografica estricta, la instalacion de una Root CA en el sistema requiere confirmacion obligatoria (no se omite con -Force)." -ForegroundColor Yellow
            }
            Write-Host "`n[CONFIRMACION REQUERIDA]" -ForegroundColor Yellow
            Write-Host "Desea autorizar la instalacion de esta Root CA en su almacen personal '$StorePath'?"
        }
        $response = Read-Host "Escriba 'CONFIRMAR' para proceder [CONFIRMAR/N]"
        $respClean = if ($response) { $response.Trim().ToLowerInvariant() } else { "" }
        if ($respClean -ne 'confirmar') {
            if (-not $Json) {
                Write-Warning "Operacion cancelada por el usuario. No se modifico ningun almacen de certificados."
            }
            if ($Json) {
                [PSCustomObject]@{
                    status = "CANCELLED"
                    action = "trust"
                    message = "Operacion cancelada por el usuario."
                } | ConvertTo-Json -Depth 4
            }
            exit 0
        }
    }

    # Importar certificado en el almacen indicado
    try {
        $store = [System.Security.Cryptography.X509Certificates.X509Store]::new("Root", [System.Security.Cryptography.X509Certificates.StoreLocation]::CurrentUser)
        if ($StorePath -ne "Cert:\CurrentUser\Root") {
            # Si se paso un almacen personalizado (por ejemplo, en pruebas)
            $store = [System.Security.Cryptography.X509Certificates.X509Store]::new($StorePath.Replace("Cert:\CurrentUser\", ""), [System.Security.Cryptography.X509Certificates.StoreLocation]::CurrentUser)
        }
        $store.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
        $store.Add($cert)
        $store.Close()
    } catch {
        # Si .NET X509Store falla, intentar con Import-Certificate de PowerShell
        try {
            Import-Certificate -FilePath $CertPath -CertStoreLocation $StorePath | Out-Null
        } catch {
            $errMsg = "Fallo al importar el certificado en '$StorePath': $_"
            if ($Json) {
                [PSCustomObject]@{
                    status = "IMPORT_FAILED"
                    action = "trust"
                    store_path = $StorePath
                    error = $errMsg
                } | ConvertTo-Json -Depth 4
                exit 1
            } else {
                Write-Error $errMsg
                exit 1
            }
        }
    }

    # Verificacion post-instalacion
    $postInstalled = $false
    if (Test-Path -LiteralPath $StorePath) {
        $updatedCerts = Get-ChildItem -Path $StorePath -ErrorAction SilentlyContinue
        foreach ($uc in $updatedCerts) {
            try {
                if ((Get-CertSha256 -Certificate $uc) -eq $actualFp) {
                    $postInstalled = $true
                    break
                }
            } catch { }
        }
    }

    if (-not $postInstalled) {
        $errMsg = "Verificacion post-instalacion fallida: el certificado no se encontro en '$StorePath' tras la operacion."
        if ($Json) {
            [PSCustomObject]@{
                status = "VERIFICATION_FAILED"
                action = "trust"
                store_path = $StorePath
                error = $errMsg
            } | ConvertTo-Json -Depth 4
            exit 1
        } else {
            Write-Error $errMsg
            exit 1
        }
    }

    if ($Json) {
        [PSCustomObject]@{
            status = "SUCCESS"
            action = "trust"
            cert_path = $CertPath
            store_path = $StorePath
            sha256_fingerprint = $actualFp
            message = "Certificado instalado y verificado exitosamente."
        } | ConvertTo-Json -Depth 4
    } else {
        Write-Host "`n[OK] Certificado Root CA de VIGIA instalado y verificado exitosamente en '$StorePath'." -ForegroundColor Green
        Write-Host "Los navegadores del usuario reconoceran ahora la autoridad HTTPS de VIGIA.`n" -ForegroundColor Green
    }
    exit 0
}

# ----------------------------------------------------------------------
# ACCION: UNTRUST o REMOVE (Reversion Segura y Estricta)
# ----------------------------------------------------------------------
if ($Action -in @('untrust', 'remove')) {
    if (-not $isInstalled -or -not $matchingStoreCert) {
        if ($Json) {
            [PSCustomObject]@{
                status = "NOT_INSTALLED"
                action = "untrust"
                store_path = $StorePath
                sha256_fingerprint = $actualFp
                message = "El certificado no se encuentra instalado en '$StorePath'. No hay nada que revertir."
            } | ConvertTo-Json -Depth 4
        } else {
            Write-Host "`n[INFO] El certificado Root CA de VIGIA (SHA-256: $actualFp) NO esta instalado en '$StorePath'." -ForegroundColor Cyan
            Write-Host "No existe ningun certificado que revertir.`n"
        }
        exit 0
    }

    # Mostrar informacion antes de remocion
    if (-not $Json) {
        Write-Host "========================================================================" -ForegroundColor Magenta
        Write-Host " VIGIA Vision Systems - Reversion Segura de Confianza (TLS-02B-R2)" -ForegroundColor Magenta
        Write-Host "========================================================================" -ForegroundColor Magenta
        Write-Host "Se eliminara EXCLUSIVAMENTE el certificado identificado por su huella SHA-256:"
        Write-Host "  Sujeto        : $($matchingStoreCert.Subject)"
        Write-Host "  Emisor        : $($matchingStoreCert.Issuer)"
        Write-Host "  Numero Serie  : $($matchingStoreCert.SerialNumber)"
        Write-Host "  Huella SHA-256: $actualFp"
        Write-Host "  Almacen Origen: $StorePath"
        Write-Host "------------------------------------------------------------------------"
    }

    # Confirmacion interactiva obligatoria en el almacen real
    if (-not $isTestIsolated) {
        if (-not $Json) {
            if ($Force) {
                Write-Host "`n[AVISO DE SEGURIDAD] Por directriz criptografica estricta, la remocion de una Root CA del sistema requiere confirmacion obligatoria (no se omite con -Force)." -ForegroundColor Magenta
            }
            Write-Host "`n[CONFIRMACION REQUERIDA]" -ForegroundColor Magenta
            Write-Host "Confirma la eliminacion estricta de este certificado del almacen '$StorePath'?"
        }
        $response = Read-Host "Escriba 'ELIMINAR' para proceder con la remocion [ELIMINAR/N]"
        $respClean = if ($response) { $response.Trim().ToLowerInvariant() } else { "" }
        if ($respClean -ne 'eliminar') {
            if (-not $Json) {
                Write-Warning "Operacion de reversion cancelada por el usuario. El certificado permanece intacto."
            }
            if ($Json) {
                [PSCustomObject]@{
                    status = "CANCELLED"
                    action = "untrust"
                    message = "Operacion de reversion cancelada por el usuario."
                } | ConvertTo-Json -Depth 4
            }
            exit 0
        }
    }

    # Ejecutar remocion segura utilizando exclusivamente el objeto validado previamente
    try {
        if ($matchingStoreCert -is [System.IO.FileInfo]) {
            # Almacen de prueba basado en archivos
            Remove-Item -LiteralPath $matchingStoreCert.FullName -Force -ErrorAction Stop
        } elseif ($matchingStoreCert.PSPath) {
            # Proveedor de certificados de PowerShell (Cert:\...)
            Remove-Item -LiteralPath $matchingStoreCert.PSPath -Force -ErrorAction Stop
        } else {
            # Instancia directa X509Store
            $store = [System.Security.Cryptography.X509Certificates.X509Store]::new("Root", [System.Security.Cryptography.X509Certificates.StoreLocation]::CurrentUser)
            if ($StorePath -ne "Cert:\CurrentUser\Root") {
                $store = [System.Security.Cryptography.X509Certificates.X509Store]::new($StorePath.Replace("Cert:\CurrentUser\", ""), [System.Security.Cryptography.X509Certificates.StoreLocation]::CurrentUser)
            }
            $store.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
            $store.Remove($matchingStoreCert)
            $store.Close()
        }
    } catch {
        $errMsg = "Fallo al remover el certificado de '$StorePath': $_"
        if ($Json) {
            [PSCustomObject]@{
                status = "REMOVAL_FAILED"
                action = "untrust"
                store_path = $StorePath
                error = $errMsg
            } | ConvertTo-Json -Depth 4
            exit 1
        } else {
            Write-Error $errMsg
            exit 1
        }
    }

    # Verificacion post-remocion: asegurar que ya no existe la huella SHA-256 en el almacen
    $postCheckCerts = @()
    if (Test-Path -LiteralPath $StorePath) {
        $postCheckCerts = Get-ChildItem -Path $StorePath -ErrorAction SilentlyContinue
    }
    $stillPresent = $false
    foreach ($pcc in $postCheckCerts) {
        try {
            if ((Get-CertSha256 -Certificate $pcc) -eq $actualFp) {
                $stillPresent = $true
                break
            }
        } catch { }
    }

    if ($stillPresent) {
        $errMsg = "Verificacion post-reversion fallida: el certificado aun aparece en '$StorePath'."
        if ($Json) {
            [PSCustomObject]@{
                status = "REMOVAL_VERIFICATION_FAILED"
                action = "untrust"
                store_path = $StorePath
                error = $errMsg
            } | ConvertTo-Json -Depth 4
            exit 1
        } else {
            Write-Error $errMsg
            exit 1
        }
    }

    if ($Json) {
        [PSCustomObject]@{
            status = "SUCCESS"
            action = "untrust"
            store_path = $StorePath
            sha256_fingerprint = $actualFp
            message = "Certificado revertido y eliminado exitosamente del almacen."
        } | ConvertTo-Json -Depth 4
    } else {
        Write-Host "`n[OK] Certificado Root CA de VIGIA revertido exitosamente de '$StorePath'." -ForegroundColor Green
        Write-Host "Se verifico criptograficamente que ya no esta presente en el almacen.`n" -ForegroundColor Green
    }
    exit 0
}
