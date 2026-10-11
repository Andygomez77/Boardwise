"""python -m tests.test_ui"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

from PySide6.QtCore import QEventLoop, QPoint, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from boardwise.ui.main_window import MainWindow

errors = []
QMessageBox.critical = staticmethod(lambda parent, title, message: errors.append(message))

app = QApplication([])
win = MainWindow()
win.set_source(Path(__file__).resolve().parents[1] / "data" / "sample_folder")
win.start()
loop = QEventLoop()
win.worker.done.connect(loop.quit)
win.worker.error.connect(loop.quit)
QTimer.singleShot(120_000, loop.quit)
loop.exec()

assert not errors, errors
table = win.table
assert table.rowCount() == 4, table.rowCount()
assert table.item(3, 0).text() == "TOTAL"
total = int(table.item(3, 1).text())
assert total > 0, total
assert win.count_label.text() == f"Subidas: {total}"
print("total subidas (área por defecto):", total)

# Dibujar un área con clics: coordenadas en píxeles del video
view = win.view
win.show()
app.processEvents()
win.clear_button.click()
assert view.polygon == [] and not win.start_button.isEnabled()


def click(point, double=False):
    pos = view._to_view(point).toPoint()
    (QTest.mouseDClick if double else QTest.mouseClick)(view, Qt.MouseButton.LeftButton, pos=pos)


def close_to(a, b):
    return all(abs(p - q) <= 3 for p, q in zip(a, b))


points = [(300, 200), (900, 200), (900, 700), (300, 700)]
for point in points[:3]:
    click(point)
assert len(view.polygon) == 3 and not view.closed and not win.start_button.isEnabled()
click(points[3])  # un doble clic real: primero un clic (agrega el vértice) y luego el doble clic (cierra)
click(points[3], double=True)
assert view.closed and len(view.polygon) == 4, (view.closed, view.polygon)
assert all(close_to(a, b) for a, b in zip(view.polygon, points)), view.polygon
assert win.start_button.isEnabled()

# Cerrar con un clic cerca del primer vértice
win.clear_button.click()
for point in points[:3]:
    click(point)
click((points[0][0] + 5, points[0][1] + 5))
assert view.closed and len(view.polygon) == 3, view.polygon
print("ok")
