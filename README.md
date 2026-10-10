# Monterrey Count

App de escritorio (PySide6) para contar pasajeros en videos.

## Instalar

- **Windows:** descarga `MonterreyCount-Setup.exe` del último release y ejecútalo. Como no está firmado, SmartScreen avisa: "Más información → Ejecutar de todas formas". Crea acceso directo en el escritorio.
- **Mac:** abre `MonterreyCount.dmg` y arrastra la app a Aplicaciones. La primera vez, clic derecho → Abrir.

## Desarrollo

```sh
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # en macOS: .venv/bin/pip
.venv/Scripts/python -m monterrey_count
```

Tests: `.venv/Scripts/python -m tests.test_updater` (imprime `ok`).

## Release

Cada push a `main` compila Mac y Windows con PyInstaller y publica el release `v<número de corrida>`.
La app (ya empaquetada) revisa los releases al abrir. Como el repo es privado, la primera vez pide un
token fine-grained de GitHub con permiso **Contents: read-only** solo sobre este repo; lo guarda en la
carpeta de datos del usuario (`%APPDATA%\MonterreyCount`, `~/Library/Application Support/MonterreyCount`).
