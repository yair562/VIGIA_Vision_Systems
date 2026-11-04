"""
Comprobación reproducible y estricta de conectividad HTTPS para VIGIA (TLS-02B / TLS-02D).

Distingue claramente las modalidades de validación:
- Modalidad A (Trust Anchor Explícito): Valida la cadena criptográfica contra vigia_root_ca.crt.
  Prueba la coherencia matemática de la PKI de VIGÍA (RSA, SHA-256, SAN, HTTP 200, CDP).
- Modalidad B (Confianza Nativa del Sistema Operativo Windows): Valida si el almacén de certificados
  de Windows (CryptoAPI/Schannel) reconoce la Root CA y valida la revocación mediante CRL (sin --ssl-no-revoke).

REGLA: Prohibido omitir validación TLS (sin -k, sin insecure, sin ignore_certificate_errors).
"""

import argparse
import hashlib
import json
import socket
import ssl
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any, Dict

import cryptography.x509
from cryptography.hazmat.primitives import serialization


def run_strict_check(
    root_ca_path: Path,
    port: int = 5000,
    lan_ip: str = "192.168.1.75",
    crl_port: int = 5080,
) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "root_ca_file": str(root_ca_path),
        "root_ca_exists": root_ca_path.is_file(),
        "modalidad_a_pki_targets": {},
        "modalidad_b_os_trust": {},
        "modalidad_a_passed": False,
        "modalidad_b_trusted": False,
        "crl_http_ok": False,
        "schannel_revocation_ok": False,
        "overall_success": False,
    }

    if not root_ca_path.is_file():
        report["error"] = f"Root CA no encontrada en: {root_ca_path}"
        return report

    # Calcular fingerprint de la Root CA
    ca_bytes = root_ca_path.read_bytes()
    ca_cert = cryptography.x509.load_pem_x509_certificate(ca_bytes)
    ca_fp = hashlib.sha256(ca_cert.public_bytes(serialization.Encoding.DER)).hexdigest().upper()
    report["root_ca_fingerprint_sha256"] = ca_fp

    targets = [
        {"name": "Localhost", "host": "localhost", "connect_ip": "127.0.0.1", "port": port},
        {"name": "LAN", "host": lan_ip, "connect_ip": lan_ip, "port": port},
    ]

    all_a_passed = True

    # ------------------------------------------------------------------
    # MODALIDAD A: Trust Anchor Explícito (vigia_root_ca.crt)
    # ------------------------------------------------------------------
    for tgt in targets:
        t_name = tgt["name"]
        host = tgt["host"]
        conn_ip = tgt["connect_ip"]
        t_port = tgt["port"]
        tgt_result: Dict[str, Any] = {
            "host": host,
            "ip": conn_ip,
            "port": t_port,
            "tcp_connected": False,
            "tls_handshake": False,
            "chain_validated": False,
            "hostname_validated": False,
            "http_app_status": None,
            "cdp_url": None,
        }

        # 1. TCP Check
        try:
            with socket.create_connection((conn_ip, t_port), timeout=3.0):
                tgt_result["tcp_connected"] = True
        except Exception as exc:
            tgt_result["tcp_error"] = str(exc)
            all_a_passed = False
            report["modalidad_a_pki_targets"][t_name] = tgt_result
            continue

        # 2. Strict TLS Handshake & Chain Validation with Explicit Root CA
        ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(root_ca_path))
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED

        try:
            with socket.create_connection((conn_ip, t_port), timeout=3.0) as sock:
                with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                    tgt_result["tls_handshake"] = True
                    tgt_result["tls_version"] = ssock.version()
                    tgt_result["cipher"] = ssock.cipher()
                    tgt_result["chain_validated"] = True
                    tgt_result["hostname_validated"] = True

                    peer_der = ssock.getpeercert(binary_form=True)
                    if peer_der:
                        peer_cert = cryptography.x509.load_der_x509_certificate(peer_der)
                        tgt_result["peer_subject"] = peer_cert.subject.rfc4514_string()
                        tgt_result["peer_issuer"] = peer_cert.issuer.rfc4514_string()
                        tgt_result["peer_serial"] = hex(peer_cert.serial_number)
                        tgt_result["peer_sha256"] = hashlib.sha256(peer_der).hexdigest().upper()

                        try:
                            cdp_ext = peer_cert.extensions.get_extension_for_oid(
                                cryptography.x509.ExtensionOID.CRL_DISTRIBUTION_POINTS
                            )
                            dp = cdp_ext.value[0]
                            if dp.full_name:
                                tgt_result["cdp_url"] = dp.full_name[0].value
                        except Exception:
                            tgt_result["cdp_url"] = None
        except Exception as exc:
            tgt_result["tls_error"] = str(exc)
            all_a_passed = False
            report["modalidad_a_pki_targets"][t_name] = tgt_result
            continue

        # 3. Strict HTTP GET /app with Explicit Root CA
        url = f"https://{host}:{t_port}/app"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "VIGIA-Strict-Check/1.0"})
            with urllib.request.urlopen(req, context=ctx, timeout=3.0) as resp:
                tgt_result["http_app_status"] = resp.status
                body = resp.read()
                tgt_result["http_app_bytes"] = len(body)
                tgt_result["http_app_ok"] = (resp.status == 200 and len(body) > 0)
        except Exception as exc:
            tgt_result["http_error"] = str(exc)
            all_a_passed = False

        report["modalidad_a_pki_targets"][t_name] = tgt_result

    report["modalidad_a_passed"] = all_a_passed

    # ------------------------------------------------------------------
    # MODALIDAD B: Validación con Almacén Nativo del Sistema Operativo
    # ------------------------------------------------------------------
    os_ctx = ssl.create_default_context()  # Usa el almacén de certificados de Windows
    os_ctx.check_hostname = True
    os_ctx.verify_mode = ssl.CERT_REQUIRED
    os_check_url = f"https://{lan_ip}:{port}/app"
    os_res: Dict[str, Any] = {
        "url": os_check_url,
        "trusted_by_os": False,
        "http_status": None,
        "error": None,
        "crl_url": f"http://{lan_ip}:{crl_port}/api/v1/tls/ca.crl",
        "crl_http_ok": False,
        "schannel_revocation_ok": False,
    }

    # 1. Comprobación OpenSSL nativo
    try:
        req = urllib.request.Request(os_check_url, headers={"User-Agent": "VIGIA-OS-Trust-Check/1.0"})
        with urllib.request.urlopen(req, context=os_ctx, timeout=3.0) as resp:
            os_res["trusted_by_os"] = (resp.status == 200)
            os_res["http_status"] = resp.status
            report["modalidad_b_trusted"] = True
    except Exception as exc:
        os_res["error"] = str(exc)
        report["modalidad_b_trusted"] = False

    # 2. Comprobación servidor CRL HTTP
    try:
        crl_req = urllib.request.Request(os_res["crl_url"], headers={"User-Agent": "VIGIA-CRL-Check/1.0"})
        with urllib.request.urlopen(crl_req, timeout=3.0) as crl_resp:
            crl_bytes = crl_resp.read()
            ct = crl_resp.headers.get("Content-Type", "")
            os_res["crl_http_status"] = crl_resp.status
            os_res["crl_content_type"] = ct
            os_res["crl_bytes"] = len(crl_bytes)
            os_res["crl_http_ok"] = (crl_resp.status == 200 and len(crl_bytes) > 0 and "application/pkix-crl" in ct)
            report["crl_http_ok"] = os_res["crl_http_ok"]
    except Exception as exc:
        os_res["crl_error"] = str(exc)
        os_res["crl_http_ok"] = False
        report["crl_http_ok"] = False

    # 3. Comprobación nativa Windows Schannel (curl.exe sin --ssl-no-revoke)
    try:
        proc = subprocess.run(
            ["curl.exe", "-I", os_check_url],
            capture_output=True,
            text=True,
            timeout=5,
        )
        os_res["schannel_curl_returncode"] = proc.returncode
        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()
        if proc.returncode == 0 and ("200 OK" in stdout or "HTTP/1.1 200" in stdout or "HTTP/2 200" in stdout):
            os_res["schannel_revocation_ok"] = True
            report["schannel_revocation_ok"] = True
        else:
            os_res["schannel_revocation_ok"] = False
            os_res["schannel_error"] = stderr or stdout
            report["schannel_revocation_ok"] = False
    except Exception as exc:
        os_res["schannel_revocation_ok"] = False
        os_res["schannel_error"] = str(exc)
        report["schannel_revocation_ok"] = False

    report["modalidad_b_os_trust"] = os_res
    report["overall_success"] = all_a_passed and report["modalidad_b_trusted"]
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Verificación Estricta HTTPS VIGIA (TLS-02B / TLS-02D)")
    parser.add_argument("--json", action="store_true", help="Salida en formato JSON")
    parser.add_argument("--port", type=int, default=5000, help="Puerto del servidor HTTPS VIGIA")
    parser.add_argument("--lan-ip", type=str, default="192.168.1.75", help="IP LAN objetivo")
    parser.add_argument("--crl-port", type=int, default=5080, help="Puerto HTTP de distribución CRL")
    parser.add_argument("--ca-file", type=str, default="", help="Ruta al archivo vigia_root_ca.crt")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent
    ca_file = Path(args.ca_file) if args.ca_file else repo_root / "certs" / "vigia_root_ca.crt"

    report = run_strict_check(root_ca_path=ca_file, port=args.port, lan_ip=args.lan_ip, crl_port=args.crl_port)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("=" * 76)
        print(" VIGIA Vision Systems — Auditoría Estricta HTTPS / TLS (TLS-02B / TLS-02D)")
        print("=" * 76)
        print(f"Root CA Ancla      : {report.get('root_ca_file')}")
        print(f"Huella Root CA     : {report.get('root_ca_fingerprint_sha256', 'N/A')}")
        print("-" * 76)

        print("[MODALIDAD A: Cadena Criptográfica Interna (Trust Anchor Explícito)]")
        for name, res in report.get("modalidad_a_pki_targets", {}).items():
            print(f"  Objetivo [{name}]: {res['host']} ({res['ip']}:{res['port']})")
            tcp_str = "[OK] Conectado" if res.get("tcp_connected") else f"[ERROR] {res.get('tcp_error')}"
            print(f"    1. Socket TCP        : {tcp_str}")
            tls_str = f"[OK] {res.get('tls_version')} ({res.get('cipher', [None])[0]})" if res.get("tls_handshake") else f"[ERROR] {res.get('tls_error')}"
            print(f"    2. Handshake TLS     : {tls_str}")
            chain_str = "[OK] Verificada estrictamente contra Root CA" if res.get("chain_validated") else "[ERROR] Fallo de cadena"
            print(f"    3. Cadena de Confianza: {chain_str}")
            host_str = "[OK] Hostname/IP coincide con SAN" if res.get("hostname_validated") else "[ERROR] Fallo de SAN"
            print(f"    4. Validación Host/IP: {host_str}")
            http_str = f"[OK] HTTP {res.get('http_app_status')} ({res.get('http_app_bytes')} bytes)" if res.get("http_app_ok") else f"[ERROR] {res.get('http_error')}"
            print(f"    5. GET /app          : {http_str}")
            cdp_str = f"[OK] {res.get('cdp_url')}" if res.get('cdp_url') else "[ADVERTENCIA] Sin CDP"
            print(f"    6. CRL Dist. Point   : {cdp_str}")
            print(f"    Certificado Servidor : {res.get('peer_subject')}")
            print(f"    Huella SHA-256 Serv. : {res.get('peer_sha256')}")

        print("-" * 76)
        print("[MODALIDAD B: Confianza Nativa del Sistema Operativo (Windows CryptoAPI / Schannel)]")
        os_info = report.get("modalidad_b_os_trust", {})
        if report.get("modalidad_b_trusted"):
            print("  1. Almacén Windows  : [OK] CONFIANZA NATIVA ACTIVA (El sistema reconoce la CA)")
            print(f"     Petición al Host : HTTP {os_info.get('http_status')} sin advertencias")
        else:
            print("  1. Almacén Windows  : [PENDIENTE / NO CONFIABLE AÚN EN WINDOWS]")
            print(f"     Causa Esperada   : {os_info.get('error')}")

        crl_stat = f"[OK] HTTP 200 ({os_info.get('crl_bytes', 0)} bytes, {os_info.get('crl_content_type')})" if os_info.get("crl_http_ok") else f"[ERROR] {os_info.get('crl_error', 'Inaccesible')}"
        print(f"  2. Servidor CRL HTTP: {crl_stat}")

        schannel_stat = "[OK] HTTP 200 OK (Revocación comprobada exitosamente sin omitir validación)" if os_info.get("schannel_revocation_ok") else f"[ERROR] {os_info.get('schannel_error')}"
        print(f"  3. Schannel Windows : {schannel_stat}")

        print("=" * 76)
        if report.get("modalidad_a_passed") and report.get("schannel_revocation_ok"):
            print("[RESULTADO TÉCNICO] PKI Y COMPROBACIÓN DE REVOCACIÓN WINDOWS APROBADAS AL 100%.")
        elif report.get("modalidad_a_passed"):
            print("[RESULTADO TÉCNICO] MODALIDAD A (PKI INTERNA) APROBADA. MODALIDAD B REQUIERE SERVICIO ACTIVO.")
        else:
            print("[RESULTADO TÉCNICO] MODALIDAD A FALLÓ.")
        print("=" * 76)

    sys.exit(0 if report.get("modalidad_a_passed") else 1)


if __name__ == "__main__":
    main()
