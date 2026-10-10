# Boardwise

App de escritorio (PySide6) para contar pasajeros en videos.

## Desarrollo

```sh
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # en macOS: .venv/bin/pip
.venv/Scripts/python -m boardwise
```

Tests: `.venv/Scripts/python -m tests.test_updater` (imprime `ok`).

## Release

Cada push a `main` compila Mac y Windows con PyInstaller y publica el release `v<número de corrida>`.
La app (ya empaquetada) revisa los releases al abrir. Como el repo es privado, la primera vez pide un
token fine-grained de GitHub con permiso **Contents: read-only** solo sobre este repo; lo guarda en la
carpeta de datos del usuario (`%APPDATA%\Boardwise`, `~/Library/Application Support/Boardwise`).
