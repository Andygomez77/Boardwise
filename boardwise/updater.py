"""Auto-actualización desde los GitHub Releases del repo (público: sin token)."""
import json
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import certifi


REPO = "Andygomez77/Boardwise"
ASSET = "mac.zip" if sys.platform == "darwin" else "windows.zip"
# certifi: el Python empaquetado no siempre encuentra los certificados del sistema
_SSL = ssl.create_default_context(cafile=certifi.where())


def current_version() -> int:
    try:
        return int((Path(getattr(sys, "_MEIPASS", ".")) / "VERSION").read_text().strip())
    except (OSError, ValueError):
        return 0


def _open(url, accept="application/vnd.github+json", timeout=10):
    req = urllib.request.Request(url, headers={"Accept": accept})
    return urllib.request.urlopen(req, context=_SSL, timeout=timeout)


def check():
    """(versión, url del asset) si hay una versión más nueva; si no, None."""
    with _open(f"https://api.github.com/repos/{REPO}/releases/latest") as r:
        release = json.load(r)
    latest = int(release["tag_name"].lstrip("v"))
    asset = next((a for a in release["assets"] if a["name"] == ASSET), None)
    if latest <= current_version() or asset is None:
        return None
    return latest, asset["url"]


def install_dir() -> Path:
    exe = Path(sys.executable).resolve()
    return exe.parents[2] if sys.platform == "darwin" else exe.parent  # el .app / la carpeta del .exe


def apply(asset_url, on_progress=lambda pct: None) -> None:
    """Descarga la versión nueva y lanza el script que la instala cuando esta app se cierre."""
    app = install_dir()
    staging = app.parent / ".boardwise_update"  # mismo disco que la app: el move es un rename
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir()
    zip_path = staging / ASSET
    with _open(asset_url, accept="application/octet-stream", timeout=60) as r, open(zip_path, "wb") as f:
        total, done = int(r.headers.get("Content-Length") or 0), 0
        while chunk := r.read(1 << 20):
            f.write(chunk)
            done += len(chunk)
            if total:
                on_progress(done * 100 // total)
    if sys.platform == "darwin":
        # ditto conserva los symlinks y permisos del .app; zipfile no
        subprocess.run(["ditto", "-x", "-k", str(zip_path), str(staging)], check=True)
    else:
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(staging)
    zip_path.unlink()
    new = next(staging.iterdir())
    old = app.with_name(app.name + ".old")
    pid = os.getpid()

    # Espera a que la app cierre, cambia vieja por nueva (si falla, restaura la vieja) y reabre.
    if sys.platform == "darwin":
        script = Path(tempfile.gettempdir()) / "boardwise_update.sh"
        script.write_text(f"""#!/bin/sh
while kill -0 {pid} 2>/dev/null; do sleep 0.5; done
rm -rf "{old}"
mv "{app}" "{old}" && {{ mv "{new}" "{app}" || mv "{old}" "{app}"; }}
rm -rf "{old}" "{staging}"
open "{app}"
""")
        subprocess.Popen(["/bin/sh", str(script)], start_new_session=True)
    else:
        script = Path(tempfile.gettempdir()) / "boardwise_update.bat"
        # ping como sleep: timeout falla sin consola. "oem": la codepage con la que cmd lee el .bat
        script.write_text(f"""@echo off
:wait
tasklist /FI "PID eq {pid}" | find "{pid}" >nul && (ping -n 2 127.0.0.1 >nul & goto wait)
rmdir /s /q "{old}" 2>nul
move "{app}" "{old}" >nul && (move "{new}" "{app}" >nul || move "{old}" "{app}" >nul)
rmdir /s /q "{old}" "{staging}"
start "" "{app}\\{Path(sys.executable).name}"
""", encoding="oem")
        subprocess.Popen(["cmd", "/c", str(script)], creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
