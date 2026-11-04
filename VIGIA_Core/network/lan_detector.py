"""
VIGIA_Core.network.lan_detector
===============================
Módulo centralizado de detección y diagnóstico pasivo de interfaces de red LAN
para VIGÍA Vision Systems (VIGIA-NET-01 / VIGIA-NET-02).

Responsabilidades:
- Identificar de manera determinista las interfaces físicas activas (Ethernet / Wi-Fi)
  con direcciones IPv4 privadas válidas (RFC 1918).
- Excluir de forma estricta adaptadores virtuales (WSL, Hyper-V, VMware, Docker, VirtualBox),
  interfaces de loopback local (127.0.0.0/8) y direcciones APIPA / link-local (169.254.0.0/16).
- Determinar la interfaz y dirección LAN recomendada según la tabla de enrutamiento del kernel.
- Resolver y validar las URLs de acceso local, LAN y URL efectiva para el QR de enrolamiento móvil.
- Proporcionar telemetría y reportes estructurados de diagnóstico pasivo de red y sondeo local de sockets.

Aislamiento arquitectónico:
- Independiente de frameworks web (prohibido importar Flask o Werkzeug).
- Depende exclusivamente de bibliotecas estándar de Python y `psutil`.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import logging
import os
import socket
import subprocess
import sys
import urllib.parse
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

VIRTUAL_INTERFACE_KEYWORDS: Tuple[str, ...] = (
    "vethernet",
    "wsl",
    "hyper-v",
    "vmware",
    "virtualbox",
    "bluetooth",
    "loopback",
    "pseudo",
    "tap",
    "tun",
    "vpn",
    "docker",
)


class NetworkDiscoveryError(Exception):
    """Excepción para errores en la identificación o resolución de interfaces de red."""
    pass


class NoLanAddressError(RuntimeError):
    """Lanzada cuando no se detecta ninguna interfaz LAN física accesible para dispositivos móviles."""
    pass


def is_usable_ipv4(ip_str: str) -> bool:
    """
    Verifica si una cadena es una dirección IPv4 utilizable para comunicación de red local.
    Excluye loopback (127.0.0.0/8), APIPA/link-local (169.254.0.0/16), 0.0.0.0 y multicast.
    """
    if not ip_str or not isinstance(ip_str, str):
        return False
    try:
        ip_obj = ipaddress.IPv4Address(ip_str.strip())
        return not (
            ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_unspecified
            or ip_obj.is_multicast
        )
    except (ipaddress.AddressValueError, ValueError):
        return False


def get_default_route_ip() -> Optional[str]:
    """
    Determina la IP local de la interfaz física utilizada por el sistema operativo
    para enrutar tráfico hacia la red externa o el router predeterminado.
    Consulta la tabla de enrutamiento del kernel vía socket UDP (sin transmisión real de datos).
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            candidate = s.getsockname()[0]
            ip_obj = ipaddress.IPv4Address(candidate)
            if ip_obj.is_private and not ip_obj.is_loopback:
                return candidate
        finally:
            s.close()
    except Exception:
        pass
    return None


def get_windows_wlan_interfaces() -> Dict[str, str]:
    """
    Consulta las interfaces inalámbricas 802.11 registradas en Windows mediante netsh wlan.
    Retorna un diccionario {nombre_interfaz: estado} (ej. {'Wi-Fi': 'connected'}).
    """
    try:
        res = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True,
            text=True,
            check=False,
            timeout=3,
        )
        if res.returncode != 0:
            return {}
        interfaces: Dict[str, str] = {}
        current_name: Optional[str] = None
        for line in res.stdout.splitlines():
            line_str = line.strip()
            if line_str.startswith("Name") or line_str.startswith("Nombre"):
                parts = line_str.split(":", 1)
                if len(parts) == 2:
                    current_name = parts[1].strip()
            elif line_str.startswith("State") or line_str.startswith("Estado"):
                parts = line_str.split(":", 1)
                if len(parts) == 2 and current_name:
                    interfaces[current_name] = parts[1].strip().lower()
        return interfaces
    except Exception as exc:
        logger.debug("No fue posible consultar interfaces wlan mediante netsh: %s", exc)
        return {}


def get_local_ipv4_addresses() -> Set[str]:
    """
    Retorna el conjunto de direcciones IPv4 locales asignadas a interfaces de red activas.
    Incluye siempre '127.0.0.1' (loopback local).
    Combina la API de adaptadores del sistema (psutil) con la resolución de host.
    """
    addresses: Set[str] = {"127.0.0.1"}
    try:
        import psutil
        for _if_name, addr_list in psutil.net_if_addrs().items():
            for addr in addr_list:
                if getattr(addr.family, "name", "") == "AF_INET" or addr.family == socket.AF_INET:
                    if addr.address:
                        addresses.add(addr.address)
    except Exception as exc:
        logger.debug("Error al consultar adaptadores mediante psutil: %s", exc)

    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, family=socket.AF_INET):
            ip_val = info[4][0]
            if ip_val:
                addresses.add(ip_val)
    except Exception as exc:
        logger.debug("Error al consultar adaptadores locales mediante getaddrinfo: %s", exc)

    return addresses


def discover_wifi_ipv4(preferred_interface: Optional[str] = None) -> Tuple[str, str]:
    """
    Identifica de manera fiable la interfaz Wi-Fi física activa y su dirección IPv4 utilizable en Windows.

    Excluye:
    - Direcciones de loopback (127.0.0.0/8).
    - Direcciones APIPA / link-local (169.254.0.0/16).
    - Direcciones no asignadas o 0.0.0.0.
    - Adaptadores Ethernet, virtuales (WSL, VMware, VirtualBox), VPN o Bluetooth.
    """
    import psutil

    target_pref = preferred_interface or os.environ.get("VIGIA_WIFI_INTERFACE")
    if target_pref:
        target_pref = target_pref.strip()

    all_addrs = psutil.net_if_addrs()
    all_stats = psutil.net_if_stats()
    ingest_mod = sys.modules.get("VIGIA_API.ingest_service")
    _get_wlan = (
        getattr(ingest_mod, "get_windows_wlan_interfaces", None)
        if ingest_mod is not None
        else None
    ) or get_windows_wlan_interfaces
    wlan_states = _get_wlan()
    wifi_candidates: Dict[str, str] = {}

    for if_name, addr_list in all_addrs.items():
        lower_name = if_name.lower()

        if any(exc in lower_name for exc in [
            "ethernet", "vethernet", "vmware", "virtualbox", "bluetooth",
            "loopback", "pseudo", "tap", "tun", "vpn"
        ]):
            continue

        is_wlan = if_name in wlan_states or any(
            pattern in lower_name for pattern in ["wi-fi", "wifi", "wlan", "wireless", "inalámbric"]
        )
        if not is_wlan:
            continue

        st = all_stats.get(if_name)
        is_up = st.isup if st else False
        netsh_state = wlan_states.get(if_name, "")
        if netsh_state in ["disconnected", "desconectado"]:
            is_up = False

        if not is_up:
            continue

        for addr in addr_list:
            if getattr(addr.family, "name", "") == "AF_INET" or addr.family == socket.AF_INET:
                if is_usable_ipv4(addr.address):
                    wifi_candidates[if_name] = addr.address
                    break

    if target_pref:
        if target_pref in wifi_candidates:
            return target_pref, wifi_candidates[target_pref]
        raise NetworkDiscoveryError(
            f"La interfaz Wi-Fi preferida '{target_pref}' no está disponible, conectada o no "
            f"posee una dirección IPv4 utilizable. Interfaces Wi-Fi detectadas: {list(wifi_candidates.keys())}."
        )

    if not wifi_candidates:
        raise NetworkDiscoveryError(
            "No se encontró ninguna interfaz Wi-Fi activa con dirección IPv4 utilizable. "
            "Asegúrese de que el adaptador Wi-Fi esté encendido y conectado a la red local. "
            "Por política de seguridad no se permite la sustitución automática por Ethernet."
        )

    if len(wifi_candidates) > 1:
        candidates_str = ", ".join(f"'{k}' ({v})" for k, v in wifi_candidates.items())
        raise NetworkDiscoveryError(
            f"Se detectaron múltiples interfaces Wi-Fi candidatas con IPv4 activa: {candidates_str}. "
            "Detención de seguridad: especifique la interfaz requerida mediante el parámetro "
            "'preferred_interface' o la variable de entorno 'VIGIA_WIFI_INTERFACE'."
        )

    selected_name, selected_ip = next(iter(wifi_candidates.items()))
    return selected_name, selected_ip


def discover_all_lan_candidates(preferred_interface: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Descubre dinámicamente todas las interfaces físicas de red local (LAN / Wi-Fi / Ethernet)
    activas con IPv4 privada (RFC 1918), excluyendo adaptadores virtuales y loopback.
    Determina cuál es la interfaz recomendada según la ruta predeterminada o la configuración.
    """
    import psutil

    target_pref = (
        preferred_interface
        or os.environ.get("VIGIA_LAN_INTERFACE")
        or os.environ.get("VIGIA_WIFI_INTERFACE")
        or ""
    ).strip().lower()

    # Permitir compatibilidad con parches y mocks existentes en VIGIA_API.ingest_service
    route_func = get_default_route_ip
    ingest_mod = sys.modules.get("VIGIA_API.ingest_service")
    if ingest_mod and hasattr(ingest_mod, "get_default_route_ip"):
        route_func = getattr(ingest_mod, "get_default_route_ip")
    default_route_ip = route_func()

    all_addrs = psutil.net_if_addrs()
    all_stats = psutil.net_if_stats()
    candidates: List[Dict[str, Any]] = []

    for if_name, addr_list in all_addrs.items():
        lower_name = if_name.lower()
        if any(exc in lower_name for exc in VIRTUAL_INTERFACE_KEYWORDS):
            continue

        st = all_stats.get(if_name)
        if not (st and st.isup):
            continue

        for addr in addr_list:
            if getattr(addr.family, "name", "") == "AF_INET" or addr.family == socket.AF_INET:
                if is_usable_ipv4(addr.address):
                    ip_obj = ipaddress.IPv4Address(addr.address)
                    if ip_obj.is_private:
                        candidates.append({
                            "interface": if_name,
                            "ip": addr.address,
                            "is_recommended": False,
                        })
                        break

    if not candidates:
        return []

    recommended_idx = -1
    if target_pref:
        for idx, c in enumerate(candidates):
            if target_pref in c["interface"].lower() or target_pref == c["ip"]:
                recommended_idx = idx
                break

    if recommended_idx == -1 and default_route_ip:
        for idx, c in enumerate(candidates):
            if c["ip"] == default_route_ip:
                recommended_idx = idx
                break

    if recommended_idx == -1:
        recommended_idx = 0

    candidates[recommended_idx]["is_recommended"] = True
    return candidates


def discover_lan_ipv4(preferred_interface: Optional[str] = None) -> Tuple[str, str]:
    """
    Resuelve la interfaz de red local (LAN) física activa y su dirección IPv4 privada RFC 1918.
    Prioriza Wi-Fi activa mediante ``discover_wifi_ipv4`` si está configurada o disponible, y si no,
    selecciona la interfaz LAN física activa recomendada excluyendo adaptadores virtuales.
    """
    try:
        return discover_wifi_ipv4(preferred_interface=preferred_interface)
    except NetworkDiscoveryError:
        if preferred_interface:
            raise

    candidates = discover_all_lan_candidates(preferred_interface=preferred_interface)
    if not candidates:
        raise NetworkDiscoveryError(
            "No se encontró ninguna interfaz Wi-Fi ni LAN física activa con IPv4 privada utilizable."
        )

    recommended = next((c for c in candidates if c.get("is_recommended")), candidates[0])
    return recommended["interface"], recommended["ip"]


def validate_public_base_url(url_str: str, require_tls: bool = False) -> str:
    """
    Valida y normaliza la URL base pública o LAN explícitamente configurada (VIGIA_PUBLIC_BASE_URL).

    Criterios de seguridad estrictos (VIGIA-NET-01):
    - Esquema admitido: http o https. Si require_tls=True, obligatoriamente https.
    - Rechaza credenciales incrustadas (usuario:contraseña@host).
    - Host no vacío, prohibiendo 0.0.0.0 y ::.
    - Rechaza parámetros de consulta (?) y fragmentos (#).
    - Normaliza removiendo barras finales.
    """
    if not url_str or not isinstance(url_str, str):
        raise ValueError("La URL base pública no puede estar vacía.")

    cleaned = url_str.strip()
    parsed = urllib.parse.urlsplit(cleaned)

    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"Esquema de URL no permitido: '{parsed.scheme}'. Solo se admite 'http' o 'https'."
        )
    if require_tls and parsed.scheme != "https":
        raise ValueError(
            "Política de seguridad TLS activa: VIGIA_PUBLIC_BASE_URL debe utilizar el esquema 'https://'."
        )
    if parsed.username or parsed.password:
        raise ValueError(
            "Por seguridad, VIGIA_PUBLIC_BASE_URL no puede contener credenciales ni usuarios embebidos."
        )
    if not parsed.hostname:
        raise ValueError("VIGIA_PUBLIC_BASE_URL debe contener un nombre de host o dirección IP válida.")
    if parsed.hostname in ("0.0.0.0", "::"):
        raise ValueError(
            "VIGIA_PUBLIC_BASE_URL no puede utilizar '0.0.0.0' ni direcciones no especificadas."
        )
    if parsed.query or parsed.fragment:
        raise ValueError(
            "VIGIA_PUBLIC_BASE_URL debe ser solo una URL base sin parámetros de consulta (?) ni fragmentos (#)."
        )

    port_part = f":{parsed.port}" if parsed.port else ""
    path_part = parsed.path.rstrip("/")
    return f"{parsed.scheme}://{parsed.hostname}{port_part}{path_part}"


def resolve_access_urls(
    port: int,
    tls_enabled: bool = False,
    app_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Resuelve de forma determinista las direcciones de acceso local, LAN y URL efectiva para QR.
    Aplica la precedencia:
    1. VIGIA_PUBLIC_BASE_URL (si está configurada y es válida).
    2. Dirección LAN física recomendada autodescubierta dinámicamente.
    3. Fallback de entorno de prueba si app_config['TESTING'] está activo.
    """
    scheme = "https" if tls_enabled else "http"
    local_url = f"{scheme}://127.0.0.1:{port}"

    candidates = discover_all_lan_candidates()
    lan_urls = [f"{scheme}://{c['ip']}:{port}" for c in candidates]
    recommended_candidate = next((c for c in candidates if c.get("is_recommended")), None)
    recommended_lan_url = (
        f"{scheme}://{recommended_candidate['ip']}:{port}" if recommended_candidate else None
    )

    public_base_url = None
    raw_public = os.environ.get("VIGIA_PUBLIC_BASE_URL", "").strip()
    if raw_public:
        public_base_url = validate_public_base_url(raw_public, require_tls=tls_enabled)

    effective_qr_base_url = public_base_url or recommended_lan_url

    is_testing = bool(app_config and app_config.get("TESTING"))
    if not effective_qr_base_url and is_testing:
        effective_qr_base_url = f"{scheme}://192.168.1.100:{port}"
        lan_urls = [effective_qr_base_url]
        recommended_lan_url = effective_qr_base_url

    return {
        "local_url": local_url,
        "lan_urls": lan_urls,
        "recommended_lan_url": recommended_lan_url,
        "public_base_url": public_base_url,
        "effective_qr_base_url": effective_qr_base_url,
        "port": port,
        "tls_enabled": tls_enabled,
        "candidates": candidates,
    }


def probe_local_port(host: str = "127.0.0.1", port: int = 5000, timeout: float = 0.5) -> bool:
    """
    Verifica de forma pasiva y rápida si el socket TCP local en host:port está aceptando conexiones.
    No transmite datos de aplicación ni modifica sockets del sistema.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            res = s.connect_ex((host, port))
            return res == 0
        finally:
            s.close()
    except Exception:
        return False


def get_lan_diagnostic_report(
    port: int = 5000,
    preferred_interface: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Construye un informe pasivo y determinista del estado de interfaces de red física y virtual,
    dirección recomendada, URLs calculadas y estado del socket local.
    """
    import psutil

    all_addrs = psutil.net_if_addrs()
    all_stats = psutil.net_if_stats()

    inspected_interfaces: List[Dict[str, Any]] = []
    filtered_virtual: List[Dict[str, Any]] = []

    for if_name, addr_list in all_addrs.items():
        st = all_stats.get(if_name)
        is_up = bool(st and st.isup)
        lower_name = if_name.lower()

        is_virtual = any(exc in lower_name for exc in VIRTUAL_INTERFACE_KEYWORDS)

        ipv4_list: List[str] = []
        for addr in addr_list:
            if getattr(addr.family, "name", "") == "AF_INET" or addr.family == socket.AF_INET:
                if addr.address:
                    ipv4_list.append(addr.address)

        for ip_addr in ipv4_list:
            is_usable = is_usable_ipv4(ip_addr)
            is_private = False
            try:
                is_private = ipaddress.IPv4Address(ip_addr).is_private
            except Exception:
                pass

            filter_reason = None
            if is_virtual:
                filter_reason = "Adaptador virtual / contenedor / túnel"
            elif not is_up:
                filter_reason = "Interfaz desconectada o inactiva"
            elif not is_usable:
                if ip_addr.startswith("127."):
                    filter_reason = "Dirección de loopback local"
                elif ip_addr.startswith("169.254."):
                    filter_reason = "Dirección APIPA / link-local sin router"
                else:
                    filter_reason = "IPv4 no utilizable para LAN"
            elif not is_private:
                filter_reason = "Dirección IPv4 pública no RFC 1918"

            entry = {
                "interface": if_name,
                "ip": ip_addr,
                "is_up": is_up,
                "is_virtual": is_virtual,
                "is_usable": is_usable and is_private and is_up and (not is_virtual),
                "filter_reason": filter_reason,
            }
            inspected_interfaces.append(entry)

            if is_virtual or (filter_reason and "loopback" not in filter_reason.lower()):
                filtered_virtual.append(entry)

    candidates = discover_all_lan_candidates(preferred_interface=preferred_interface)
    recommended = next((c for c in candidates if c.get("is_recommended")), None)
    default_route = get_default_route_ip()
    is_listening = probe_local_port(host="127.0.0.1", port=port)

    raw_tls = os.environ.get("VIGIA_ENABLE_TLS", "0").strip().lower()
    tls_enabled = raw_tls in {"1", "true", "yes", "on"}

    access_urls = resolve_access_urls(port=port, tls_enabled=tls_enabled)

    return {
        "ok": len(candidates) > 0,
        "default_route_ip": default_route,
        "recommended_candidate": recommended,
        "candidates": candidates,
        "filtered_virtual": filtered_virtual,
        "inspected_interfaces": inspected_interfaces,
        "access_urls": access_urls,
        "port": port,
        "tls_enabled": tls_enabled,
        "socket_listening_127_0_0_1": is_listening,
    }


def main() -> int:
    """Punto de entrada de línea de comandos para diagnósticos de red."""
    parser = argparse.ArgumentParser(
        description="Diagnóstico pasivo de interfaces de red LAN de VIGÍA Vision Systems."
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("VIGIA_DEV_PORT", "5000")),
        help="Puerto TCP del servidor VIGÍA (por omisión 5000).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emite el informe en formato JSON estructurado.",
    )
    args = parser.parse_args()

    report = get_lan_diagnostic_report(port=args.port)

    if args.json:
        sys.stdout.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        return 0 if report["ok"] else 1

    sys.stdout.write("=" * 70 + "\n")
    sys.stdout.write(" VIGÍA Vision Systems — Diagnóstico Pasivo de Red LAN (VIGIA-NET-02)\n")
    sys.stdout.write("=" * 70 + "\n\n")

    sys.stdout.write("1. INTERFACES LAN CANDIDATAS (FÍSICAS ACTIVAS):\n")
    if report["candidates"]:
        for c in report["candidates"]:
            rec_badge = " [RECOMENDADA]" if c.get("is_recommended") else ""
            sys.stdout.write(f"   - {c['interface']}: {c['ip']}{rec_badge}\n")
    else:
        sys.stdout.write("   [ADVERTENCIA] No se detectó ninguna interfaz física LAN con IPv4 privada activa.\n")

    sys.stdout.write("\n2. RUTA EXTERNA PREDETERMINADA DEL KERNEL:\n")
    sys.stdout.write(f"   - IP local de salida: {report['default_route_ip'] or 'No detectada'}\n")

    sys.stdout.write("\n3. ADAPTADORES VIRTUALES / EXCLUIDOS:\n")
    if report["filtered_virtual"]:
        for f in report["filtered_virtual"]:
            sys.stdout.write(f"   - {f['interface']} ({f['ip']}): {f['filter_reason']}\n")
    else:
        sys.stdout.write("   - Ninguno detectado.\n")

    sys.stdout.write("\n4. URLS DE ACCESO CALCULADAS:\n")
    sys.stdout.write(f"   - Local:         {report['access_urls']['local_url']}\n")
    sys.stdout.write(f"   - LAN Principal: {report['access_urls']['recommended_lan_url'] or 'N/A'}\n")
    sys.stdout.write(f"   - Enrolamiento:  {report['access_urls']['effective_qr_base_url'] or 'N/A'}\n")
    sys.stdout.write(f"   - TLS Activo:    {'Sí (HTTPS)' if report['tls_enabled'] else 'No (HTTP plano)'}\n")

    sys.stdout.write("\n5. SONDEO PASIVO DE SOCKET LOCAL:\n")
    listen_str = "Activo (Aceptando conexiones en 127.0.0.1)" if report["socket_listening_127_0_0_1"] else "Inactivo (Sin proceso escuchando)"
    sys.stdout.write(f"   - Puerto TCP {report['port']}: {listen_str}\n")
    sys.stdout.write("=" * 70 + "\n")

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
