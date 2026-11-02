"""
VIGIA_Core.config.env_loader
============================
Carga centralizada (CFG-01) del único archivo de configuración local
``Software/.env``.

Reglas:
- Ubicación determinista respecto a este archivo (no depende del directorio de
  trabajo). Se puede sustituir con la variable ``VIGIA_ENV_FILE``.
- Las variables ya definidas en el entorno del proceso tienen precedencia sobre
  el archivo (``override=False``).
- Nunca se registran ni se incluyen valores en mensajes de error; solo nombres.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Iterable, Optional

from dotenv import dotenv_values, load_dotenv

# .../Software/VIGIA_Vision_Systems/VIGIA_Core/config/env_loader.py -> .../Software
PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]


class MissingConfigurationError(RuntimeError):
    """Falta una variable de configuración obligatoria (solo se indica el nombre)."""


def env_file_path() -> Path:
    override = os.environ.get("VIGIA_ENV_FILE", "").strip()
    return Path(override).resolve() if override else (PROJECT_ROOT / ".env")


def read_env_file() -> Dict[str, str]:
    """Lee el archivo ``.env`` global sin modificar ``os.environ``."""
    path = env_file_path()
    if not path.is_file():
        return {}
    return {k: v for k, v in dotenv_values(path, encoding="utf-8").items() if v is not None}


def load_project_env() -> Optional[Path]:
    """
    Vuelca ``Software/.env`` en ``os.environ`` sin sobrescribir valores del proceso.
    Retorna la ruta cargada o ``None`` si el archivo no existe.
    """
    path = env_file_path()
    if not path.is_file():
        return None
    load_dotenv(path, override=False, encoding="utf-8")
    return path


def get_setting(name: str, default: Optional[str] = None) -> Optional[str]:
    """Entorno del proceso primero; después ``Software/.env``; después ``default``."""
    val = os.environ.get(name)
    if val is not None and val.strip() != "":
        return val
    val = read_env_file().get(name)
    if val is not None and val.strip() != "":
        return val
    return default


def require_settings(names: Iterable[str]) -> None:
    """Lanza ``MissingConfigurationError`` listando los nombres faltantes."""
    missing = [n for n in names if not get_setting(n)]
    if missing:
        raise MissingConfigurationError(
            "Faltan variables de configuración obligatorias: "
            f"{', '.join(missing)}. Defínalas en '{env_file_path()}' "
            "(plantilla: Software/.env.example) o en el entorno del proceso."
        )
