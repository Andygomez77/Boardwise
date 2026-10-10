"""Carpeta de datos del usuario. El actualizador reemplaza la carpeta de la app, así que nada del usuario vive ahí."""
import os
import sys
from pathlib import Path


def data_dir() -> Path:
    if sys.platform == "darwin":
        d = Path.home() / "Library" / "Application Support" / "MonterreyCount"
    elif sys.platform == "win32":
        d = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "MonterreyCount"
    else:
        d = Path.home() / ".monterrey_count"
    d.mkdir(parents=True, exist_ok=True)
    return d
