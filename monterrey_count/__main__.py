import sys
import urllib.error

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QInputDialog, QLineEdit, QMessageBox, QProgressDialog

from monterrey_count import updater
from monterrey_count.ui.main_window import TITLE, MainWindow


def update_if_available(app) -> bool:
    """True si quedó lanzada una actualización y la app debe cerrarse."""
    if not getattr(sys, "frozen", False):
        return False  # corriendo desde el código: no hay nada que actualizar
    token = updater.load_token()
    if not token:
        token, ok = QInputDialog.getText(None, TITLE, "Token de GitHub (solo lectura) para recibir actualizaciones:",
                                         QLineEdit.EchoMode.Password)
        token = token.strip()
        if not ok or not token:
            return False
        updater.save_token(token)
    try:
        found = updater.check(token)
        if not found:
            return False
        version, url = found
        if QMessageBox.question(None, TITLE, f"Hay una versión nueva (v{version}). ¿Actualizar ahora?") \
                != QMessageBox.StandardButton.Yes:
            return False
        progress = QProgressDialog("Descargando actualización…", "", 0, 100)
        progress.setCancelButton(None)
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.show()

        def on_progress(pct):
            progress.setValue(pct)
            app.processEvents()

        updater.apply(url, token, on_progress)
        return True
    except urllib.error.HTTPError as e:
        if e.code == 401:
            updater.forget_token()
            QMessageBox.warning(None, TITLE, "El token de GitHub no es válido; se pedirá de nuevo al abrir la app.")
        else:
            QMessageBox.warning(None, TITLE, f"No se pudo buscar actualizaciones (HTTP {e.code}).")
    except urllib.error.URLError:
        pass  # sin internet: se abre la versión actual
    except Exception as e:
        QMessageBox.warning(None, TITLE, f"Falló la actualización: {e}")
    return False


def main():
    app = QApplication(sys.argv)
    if update_if_available(app):
        return
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
