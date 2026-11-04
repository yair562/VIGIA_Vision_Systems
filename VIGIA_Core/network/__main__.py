"""
VIGIA_Core.network.__main__
===========================
Punto de entrada para ejecutar diagnósticos pasivos de red mediante:
python -m VIGIA_Core.network
"""

import sys
from .lan_detector import main

if __name__ == "__main__":
    sys.exit(main())
