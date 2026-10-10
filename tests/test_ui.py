"""python -m tests.test_ui"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

from PySide6.QtCore import QEventLoop, QTimer
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
assert (table.item(3, 1).text(), table.item(3, 2).text()) == ("7", "5"), (table.item(3, 1).text(), table.item(3, 2).text())
assert win.in_label.text() == "Entradas: 7" and win.out_label.text() == "Salidas: 5"
print("ok")
