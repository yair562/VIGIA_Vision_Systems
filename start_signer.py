import sys
import os
from pathlib import Path

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root))

from VIGIA_Security.signer.daemon import main

if __name__ == "__main__":
    sys.exit(main())
