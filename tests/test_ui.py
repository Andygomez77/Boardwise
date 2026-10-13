"""python -m tests.test_ui"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEventLoop, QPoint, QSettings, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from PySide6.QtGui import QPixmap

import boardwise.ui.worker as worker_module
from boardwise.ui import style
from boardwise.core.pipeline import PARALLEL_VIDEOS, run_videos
from boardwise.ui.main_window import MainWindow, first_frame
from boardwise.ui.worker import to_qimage

errors = []
QMessageBox.critical = staticmethod(lambda parent, title, message: errors.append(message))

QSettings.setDefaultFormat(QSettings.Format.IniFormat)  # el modo guardado va a una carpeta de prueba, no al registro del usuario
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, tempfile.mkdtemp())
app = QApplication([])
style.apply(app, "dark")
win = MainWindow()
ROOT = Path(__file__).resolve().parents[1]
win.set_source(ROOT / "data" / "sample_folder")

# Tema: alterna claro/oscuro dos veces sin errores, queda guardado y cambia los colores de pintado
assert style.mode == "dark" and win.theme_button.text() == "Modo claro"
win.theme_button.click()
assert style.mode == "light" and style.C["BG"] == "#F6F4FC" and win.theme_button.text() == "Modo oscuro"
assert QSettings("Boardwise", "Boardwise").value("theme") == "light" and style.initial_mode() == "light"
assert win.logo.pixmap().height() > 0
win.theme_button.click()
assert style.mode == "dark" and QSettings("Boardwise", "Boardwise").value("theme") == "dark" and style.C["BG"] == "#120D24"
assert style.initial_mode() == "dark" and Path(style.asset("icon.png")).exists()


def wait_for(signal, ms=120_000):
    loop = QEventLoop()
    signal.connect(loop.quit)
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(ms)
    loop.exec()
    timer.stop()


def wait_until(condition, ms=60_000):
    for _ in range(ms // 50):
        if condition():
            return
        QTest.qWait(50)
    raise AssertionError("tiempo agotado")


# Línea de tiempo: las duraciones se calculan en segundo plano y la barra se habilita al terminar
assert not win.bar.isEnabled()
wait_until(lambda: win.timeline is not None)
timeline = win.timeline
assert win.bar.isEnabled() and win.play_button.isEnabled()
assert abs(timeline.total - sum(timeline.durations)) < 1e-9 and timeline.total > 0
win._scrub(timeline.offsets[1] + timeline.durations[1] / 2)  # a la mitad del 2.º archivo
assert win.bar.timeline.locate(win.position)[0].name == "segment_01.mp4"
assert win.view.pix is not None and win.cap_path.name == "segment_01.mp4"
win.fwd_10.click()
assert abs(win.position - (timeline.offsets[1] + timeline.durations[1] / 2 + 10)) < 0.3 or win.position == timeline.total
win.video_list.itemClicked.emit(win.video_list.item(2))  # clic en un video: salta a su inicio
assert abs(win.position - timeline.offsets[2]) < 0.2 and win.cap_path.name == "segment_02.mp4"
win.speed_box.setCurrentIndex(4)  # 16x: reproduce cruzando de archivo
assert win.speed == 16
win._scrub(timeline.offsets[1] - 1)
assert win.cap_path.name == "segment_00.mp4"
win.play_button.click()
assert win.playing and win.play_button.text() == "Pausa"
wait_until(lambda: win.cap_path.name == "segment_01.mp4" and win.position > timeline.offsets[1])
win.play_button.click()
assert not win.playing and win.play_button.text() == "Reproducir"
win.speed_box.setCurrentIndex(0)
win.video_list.itemClicked.emit(win.video_list.item(0))

# Sin reloj (sample_folder): solo la posición relativa, sin hora real ni inicios
assert win.wall is None and win.bar.wall is None and win.bar.starts == [None] * 3
win._scrub(timeline.offsets[1] + 3)
assert win.bar.label().startswith("segment_01 · 00:00:") and "M" not in win.bar.label(), win.bar.label()
win.video_list.itemClicked.emit(win.video_list.item(0))

# Con reloj falso en el worker: la marca guarda la hora y el tooltip la muestra
FAKE = datetime(2026, 10, 6, 13, 59, 29)
real_read_clock = worker_module.read_clock
worker_module.read_clock = lambda frame: FAKE
win.starts = {"segment_00.mp4": FAKE}


def run_to_end():
    win.start()
    wait_for(win.worker.done)
    assert not errors, errors


run_to_end()
table = win.table
assert table.rowCount() == 4, table.rowCount()
assert table.item(3, 0).text() == "TOTAL"
total = int(table.item(3, 1).text())
assert total > 0, total
assert win.count_label.text() == str(total)
print("total subidas (área por defecto):", total)

# Una marca por subida; clic en la primera: pausa y salta 2 s antes
assert len(win.bar.marks) == total, (len(win.bar.marks), total)
assert win.bar.isEnabled() and win.play_button.isEnabled()
win.show()
app.processEvents()
win.play_button.click()
first = win.bar.sorted_marks()[0]
QTest.mouseClick(win.bar, Qt.MouseButton.LeftButton, pos=QPoint(round(win.bar.x_of(first[0])) + 2, 30))
assert not win.playing
assert abs(win.position - max(first[0] - 2, 0)) < 0.2, (win.position, first)
last = win.bar.sorted_marks()[-1]
assert last[0] > 2
QTest.mouseClick(win.bar, Qt.MouseButton.LeftButton, pos=QPoint(round(win.bar.x_of(last[0])) - 2, 30))
assert abs(win.position - (last[0] - 2)) < 0.2, (win.position, last)
print("primera subida:", round(first[0], 1), "s en", first[2].name)
worker_module.read_clock = real_read_clock
assert all(mark[2] == FAKE for mark in win.bar.marks)
assert win.bar.tooltip_at(win.bar.x_of(first[0])) == f"Subida 1 · 01:59:29 PM · {first[2].stem}", win.bar.tooltip_at(win.bar.x_of(first[0]))
assert table.horizontalHeaderItem(2).text() == "Inicio"
assert table.item(0, 2).text() == "06/10/2026 01:59:29 PM" and table.item(1, 2).text() == ""
win.bar.starts[1] = FAKE  # tooltip del separador (si no hay una marca encima)
x = win.bar.x_of(timeline.offsets[1])
assert win.bar._mark_near(x) or win.bar.tooltip_at(x) == "segment_01 · 06/10/2026 01:59:29 PM", win.bar.tooltip_at(x)
win.bar.starts[1] = None

# Cada fila == lo que sumó ese video con un solo Counter compartido entre archivos (PARALLEL_VIDEOS = 1)
assert PARALLEL_VIDEOS == 1
paths = [Path(__file__).resolve().parents[1] / "data" / "sample_folder" / table.item(row, 0).text() for row in range(3)]
final = {}
for path, _, _, count, *_ in run_videos(paths, win.view.polygon):
    final[path] = count
for row, path in enumerate(paths):
    expected = final[path] - (final[paths[row - 1]] if row else 0)
    assert int(table.item(row, 1).text()) == expected, (path.name, table.item(row, 1).text(), expected)
assert total == sum(int(table.item(row, 1).text()) for row in range(3))

# Solo 2 de los 3 videos marcados: la tabla tiene exactamente esas 2 filas + TOTAL
assert win.video_list.count() == 3 and len(win._checked()) == 3
win.video_list.item(1).setCheckState(Qt.CheckState.Unchecked)
names = [win.video_list.item(0).text(), win.video_list.item(2).text()]
run_to_end()
assert [table.item(r, 0).text() for r in range(table.rowCount())] == names + ["TOTAL"], table.rowCount()
assert all(mark[2] is None for mark in win.bar.marks)  # sin reloj en los cuadros: marcas sin hora
reference = table.item(2, 1).text()
print("total con 2 videos:", reference)
win.none_button.click()
assert not win.start_button.isEnabled()
win.all_button.click()
assert win.start_button.isEnabled()
win.video_list.item(1).setCheckState(Qt.CheckState.Unchecked)

# Pausar a mitad: no llegan cuadros ni conteos en pausa; al reanudar termina con el mismo total
win.start()
assert not win.bar.isEnabled() and not win.play_button.isEnabled() and win.bar.marks == []
seen = []
win.worker.frame.connect(lambda _: seen.append("frame"))
win.worker.counts.connect(lambda _: seen.append("count"))
wait_for(win.worker.frame)
win.pause_button.click()
assert win.pause_button.text() == "Reanudar"
QTest.qWait(300)  # deja pasar lo que ya venía en camino
assert win.statusBar().currentMessage() == "En pausa"
before = len(seen)
QTest.qWait(1000)
assert len(seen) == before, (before, len(seen))
win.pause_button.click()
assert win.pause_button.text() == "Pausar"
wait_for(win.worker.done)
assert not errors, errors
assert table.item(2, 1).text() == reference, (table.item(2, 1).text(), reference)

# Al terminar, la vista vuelve al primer cuadro limpio del video seleccionado (sin cajas ni área quemada)
selected = win.video_list.currentItem().data(Qt.ItemDataRole.UserRole)
clean = QPixmap.fromImage(to_qimage(first_frame(selected))).toImage()
assert win.view.pix.toImage() == clean

# Iniciar arranca desde el video seleccionado (aunque no esté marcado) y sigue con los marcados siguientes
win.all_button.click()
win.video_list.item(1).setCheckState(Qt.CheckState.Unchecked)
win.video_list.setCurrentRow(1)
run_to_end()
assert win.video_list.item(1).checkState() == Qt.CheckState.Checked
assert [table.item(r, 0).text() for r in range(table.rowCount())] == ["segment_01.mp4", "segment_02.mp4", "TOTAL"],     [table.item(r, 0).text() for r in range(table.rowCount())]
win.video_list.setCurrentRow(0)
win.video_list.item(1).setCheckState(Qt.CheckState.Unchecked)

# Detener estando en pausa termina el hilo
win.start()
worker = win.worker
wait_for(worker.frame)
win.pause_button.click()
QTest.qWait(300)
win.stop_button.click()
assert worker.wait(5000)
app.processEvents()
assert win.start_button.isEnabled() and not win.pause_button.isEnabled()

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
assert all(close_to(a, b) for a, b in zip(view.polygon, points[:3])), view.polygon  # solo los puntos nuevos

# Archivo real del DVR (si existe): saltar a 1309.8 s de hiv00054 muestra 01:59:29 PM; la tabla y los separadores usan el inicio real
real = ROOT / "data" / "video test" / "983 06-10-2026" / "hiv00054.mp4"
if real.exists():
    dvr = MainWindow()
    dvr.show()
    dvr.set_source(real)
    wait_until(lambda: dvr.timeline is not None)
    assert dvr.starts == {"hiv00054.mp4": datetime(2026, 10, 6, 13, 37, 40)}, dvr.starts
    dvr._scrub(1309.8)
    assert dvr.wall == datetime(2026, 10, 6, 13, 59, 29), dvr.wall
    assert dvr.bar.label().startswith("06/10/2026 01:59:29 PM · hiv00054 · 00:21:"), dvr.bar.label()
    dvr.bar.add_mark(real, 1309.8, dvr.wall)
    assert dvr.bar.tooltip_at(dvr.bar.x_of(1309.8)) == "Subida 1 · 01:59:29 PM · hiv00054"
    dvr.close()
    print("reloj real: ok")

# Cerrar la ventana en pausa no se cuelga ni deja hilos de lectura colgados
threads = threading.active_count()
win.start()
worker = win.worker
wait_for(worker.frame)
win.pause_button.click()
win.close()
assert worker.isFinished()
assert threading.active_count() == threads, threading.enumerate()
print("ok")
