"""
conftest.py – Configuración global de pytest.

Añade la raíz del proyecto al sys.path para que los imports
funcionen sin instalar el paquete.
"""

import sys
from pathlib import Path

# Raíz del proyecto
sys.path.insert(0, str(Path(__file__).resolve().parent))
