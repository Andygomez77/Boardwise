import time
from pathlib import Path

import cv2
from PySide6.QtCore import QPointF, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow,
                               QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from boardwise import updater
from boardwise.core.clock import read_clock
from boardwise.core.pipeline import VIDEO_EXTENSIONS, list_videos
from boardwise.core.timeline import Timeline, seek
from boardwise.ui.timeline import DurationWorker, TimelineBar, clock_text
from boardwise.ui.worker import Worker, to_qimage

TITLE = "Boardwise"
BIG = "font-size: 28px; font-weight: bold"
PANEL_WIDTH = 260
CLOSE_PX = 10  # distancia en pantalla al primer vértice para cerrar el área
SPEEDS = (1, 2, 4, 8, 16)
TICK_MS = 33
SCRUB_INTERVAL = 0.15  # segundos entre cuadros mientras se arrastra la barra
LEAD = 2  # segundos antes de la subida a los que salta al hacer clic en su marca
CLOCK_INTERVAL = 0.5  # segundos entre lecturas de la hora real al reproducir
SEQUENTIAL_MAX = 1.0  # avances de hasta 1 s se leen cuadro a cuadro; más grandes saltan por tiempo
CALCULATING = "Calculando duración…"
SEEKING = "Buscando…"


def first_frame(path):
    capture = cv2.VideoCapture(str(path))
    ok, frame = capture.read()
    capture.release()
    return frame if ok else None


class VideoView(QWidget):
    """Muestra el cuadro escalado con su aspecto y deja trazar el área de conteo en coordenadas del video."""

    changed = Signal()

    def __init__(self):
        super().__init__()
        self.setMinimumSize(640, 360)
        self.setMouseTracking(True)
        self.pix = None
        self.polygon = []  # vértices (x, y) en píxeles del video
        self.closed = False
        self._cursor = None

    def set_frame(self, image):
        self.pix = QPixmap.fromImage(image)
        self.update()

    def _rect(self):
        size = self.pix.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        return QRect((self.width() - size.width()) // 2, (self.height() - size.height()) // 2, size.width(), size.height())

    def _to_video(self, pos):
        rect = self._rect()
        x = (pos.x() - rect.x()) / rect.width() * self.pix.width()
        y = (pos.y() - rect.y()) / rect.height() * self.pix.height()
        return round(min(max(x, 0), self.pix.width())), round(min(max(y, 0), self.pix.height()))

    def _to_view(self, point):
        rect = self._rect()
        return QPointF(rect.x() + point[0] / self.pix.width() * rect.width(),
                       rect.y() + point[1] / self.pix.height() * rect.height())

    def ready(self):
        return self.closed and len(self.polygon) >= 3

    def clear_area(self):
        self.polygon, self.closed, self._cursor = [], False, None
        self.update()
        self.changed.emit()

    def set_default_area(self):
        w, h = self.pix.width(), self.pix.height()
        self.polygon = [(w // 4, h // 4), (3 * w // 4, h // 4), (3 * w // 4, 3 * h // 4), (w // 4, 3 * h // 4)]
        self.closed = True
        self.update()
        self.changed.emit()

    def _close(self):
        if len(self.polygon) >= 3:
            self.closed = True
            self.update()
            self.changed.emit()

    def mousePressEvent(self, event):
        if not self.pix or self.closed or event.button() != Qt.MouseButton.LeftButton:
            return
        point = self._to_video(event.position())
        if len(self.polygon) >= 3:
            first = self._to_view(self.polygon[0])
            if (event.position() - first).manhattanLength() <= CLOSE_PX:
                return self._close()
        self.polygon.append(point)
        self.update()
        self.changed.emit()

    def mouseDoubleClickEvent(self, event):
        if self.pix and not self.closed:
            self._close()  # el primer clic del doble clic ya agregó el último vértice

    def mouseMoveEvent(self, event):
        if self.pix and self.polygon and not self.closed:
            self._cursor = event.position()
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        if not self.pix:
            return
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(self._rect(), self.pix)
        points = [self._to_view(point) for point in self.polygon]
        painter.setPen(QPen(QColor(0, 255, 0), 3))
        if self.closed:
            painter.setBrush(QColor(0, 255, 0, 70))
            painter.drawPolygon(QPolygonF(points))
        else:
            painter.drawPolyline(QPolygonF(points + ([self._cursor] if self._cursor and points else [])))
            painter.setBrush(QColor(0, 255, 0))
            for point in points:
                painter.drawEllipse(point, 4, 4)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{TITLE} v{updater.current_version()}")
        self.worker = None
        self.paused = False
        self.provider = ""
        self.running = set()  # posiciones (en run_items) de los videos en curso
        self.finished = 0
        self.timeline = None  # None mientras se calculan las duraciones
        self.dur_worker = None
        self.position = 0.0  # segundos desde el inicio de la carpeta
        self.wall = None  # hora real impresa en el cuadro mostrado (None = sin reloj)
        self.starts = {}  # nombre de archivo -> hora real de su primer cuadro
        self._clock_at = 0.0
        self.playing = False
        self.speed = 1
        self.scrubbing = False
        self.cap = None  # VideoCapture propio de la reproducción
        self.cap_path = None
        self.cap_t = -1e9  # segundo (en el archivo) del último cuadro leído; -1e9 = hay que saltar
        self.cap_fps = 15
        self._last_tick = self._shown = 0.0
        self.tick = QTimer(self)
        self.tick.setInterval(TICK_MS)
        self.tick.timeout.connect(self._tick)

        self.folder_button = QPushButton("Abrir carpeta…")
        self.video_button = QPushButton("Abrir video…")
        self.path_label = QLabel("Elige una carpeta o un video")
        self.view = VideoView()
        self.bar = TimelineBar()
        self.back_min = QPushButton("−1 min")
        self.back_10 = QPushButton("−10 s")
        self.play_button = QPushButton("Reproducir")
        self.fwd_10 = QPushButton("+10 s")
        self.fwd_min = QPushButton("+1 min")
        self.speed_box = QComboBox()
        self.speed_box.addItems([f"{speed}x" for speed in SPEEDS])
        self.start_button = QPushButton("Iniciar")
        self.pause_button = QPushButton("Pausar")
        self.stop_button = QPushButton("Detener")
        self.clear_button = QPushButton("Borrar área")
        self.count_label = QLabel()
        self.file_label = QLabel()
        self.video_list = QListWidget()
        self.all_button = QPushButton("Todos")
        self.none_button = QPushButton("Ninguno")
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Archivo", "Subidas", "Inicio"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMaximumHeight(180)
        self.count_label.setStyleSheet(BIG)
        read_clock(None)  # carga las plantillas aquí, antes de que otros hilos lean el reloj

        top = QHBoxLayout()
        for widget in (self.folder_button, self.video_button, self.clear_button, self.path_label):
            top.addWidget(widget)
        top.setStretch(3, 1)
        controls = QHBoxLayout()
        for widget in (self.start_button, self.pause_button, self.stop_button, self.count_label, self.file_label):
            controls.addWidget(widget)
        controls.setStretch(4, 1)
        playback = QHBoxLayout()
        for widget in (self.back_min, self.back_10, self.play_button, self.fwd_10, self.fwd_min, self.speed_box):
            playback.addWidget(widget)
        playback.addStretch(1)
        layout = QVBoxLayout()
        layout.addLayout(top)
        layout.addWidget(QLabel("Haz clic en las esquinas del área; doble clic para cerrar"))
        layout.addWidget(self.view, 1)
        layout.addWidget(self.bar)
        layout.addLayout(playback)
        layout.addLayout(controls)
        layout.addWidget(self.table)
        marks = QHBoxLayout()
        marks.addWidget(self.all_button)
        marks.addWidget(self.none_button)
        panel = QVBoxLayout()
        panel.addWidget(QLabel("Videos"))
        panel.addWidget(self.video_list, 1)
        panel.addLayout(marks)
        panel.setContentsMargins(0, 0, 0, 0)
        side = QWidget()
        side.setLayout(panel)
        side.setFixedWidth(PANEL_WIDTH)
        layout.setContentsMargins(0, 0, 0, 0)
        left = QWidget()
        left.setLayout(layout)
        central = QWidget()
        main = QHBoxLayout(central)
        main.addWidget(left, 1)
        main.addWidget(side)
        self.setCentralWidget(central)

        self.folder_button.clicked.connect(self.open_folder)
        self.video_button.clicked.connect(self.open_video)
        self.start_button.clicked.connect(self.start)
        self.pause_button.clicked.connect(self.toggle_pause)
        self.stop_button.clicked.connect(self.stop)
        self.video_list.itemClicked.connect(self.show_first_frame)
        self.bar.seek.connect(self._on_seek)
        self.bar.mark_clicked.connect(self._goto_mark)
        self.play_button.clicked.connect(self.toggle_play)
        for button, seconds in ((self.back_min, -60), (self.back_10, -10), (self.fwd_10, 10), (self.fwd_min, 60)):
            button.clicked.connect(lambda _=False, seconds=seconds: self._scrub(self.position + seconds))
        self.speed_box.currentIndexChanged.connect(lambda i: setattr(self, "speed", SPEEDS[i]))
        self.video_list.itemChanged.connect(self._update_start)
        self.all_button.clicked.connect(lambda: self._mark_all(Qt.CheckState.Checked))
        self.none_button.clicked.connect(lambda: self._mark_all(Qt.CheckState.Unchecked))
        self.clear_button.clicked.connect(self.view.clear_area)
        self.view.changed.connect(self._update_start)
        self._reset()
        self._busy(False)
        self.resize(1300, 800)

    def _reset(self):
        self.count_label.setText("Subidas: 0")
        self.file_label.clear()
        self.table.setRowCount(0)
        self.bar.clear_marks()

    def _busy(self, busy):
        for widget in (self.folder_button, self.video_button, self.view, self.clear_button):
            widget.setEnabled(not busy)
        self.stop_button.setEnabled(busy)
        self.pause_button.setEnabled(busy)
        if busy:
            self._stop_play()
        self.pause_button.setText("Pausar")
        self.paused = False
        for widget in (self.all_button, self.none_button):
            widget.setEnabled(not busy)
        for item in self._items():  # con la lista bloqueada no se pueden marcar
            flags = item.flags() | Qt.ItemFlag.ItemIsUserCheckable
            item.setFlags(flags & ~Qt.ItemFlag.ItemIsUserCheckable if busy else flags)
            item.setBackground(QBrush())
        self._update_start()
        self._update_playback()

    def _update_playback(self):
        enabled = self.timeline is not None and not self.stop_button.isEnabled()
        for widget in (self.bar, self.back_min, self.back_10, self.play_button, self.fwd_10, self.fwd_min, self.speed_box):
            widget.setEnabled(enabled)

    def _items(self):
        return [self.video_list.item(row) for row in range(self.video_list.count())]

    def _checked(self):
        return [item for item in self._items() if item.checkState() == Qt.CheckState.Checked]

    def _mark_all(self, state):
        for item in self._items():
            item.setCheckState(state)

    def _update_start(self):
        busy = self.stop_button.isEnabled()
        self.start_button.setEnabled(bool(self._checked()) and self.view.ready() and not busy)

    def open_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Abrir carpeta")
        if path:
            self.set_source(path)

    def open_video(self):
        patterns = " ".join(f"*{ext}" for ext in VIDEO_EXTENSIONS)
        path, _ = QFileDialog.getOpenFileName(self, "Abrir video", "", f"Videos ({patterns})")
        if path:
            self.set_source(path)

    def set_source(self, path):
        path = Path(path)
        videos = list_videos(path) if path.is_dir() else [path]
        for video in videos:
            frame = first_frame(video)
            if frame is not None:
                break
        else:
            QMessageBox.warning(self, TITLE, "No se pudo abrir ningún video de esa ruta.")
            return
        self.path_label.setText(f"{path}  ({len(videos)} videos)" if path.is_dir() else str(path))
        self._reset()
        self._stop_play()
        self.timeline, self.position, self.cap_path, self.cap_t = None, 0.0, None, -1e9
        self.wall, self.starts = read_clock(frame), {}
        self.bar.set_timeline(None)
        self.bar.set_position(0.0, self.wall)
        self.video_list.clear()
        for item_path in videos:
            item = QListWidgetItem(item_path.name)
            item.setData(Qt.ItemDataRole.UserRole, item_path)
            item.setCheckState(Qt.CheckState.Checked)
            self.video_list.addItem(item)
        self.video_list.setCurrentRow(videos.index(video))
        self.view.set_frame(to_qimage(frame))
        self.view.set_default_area()
        self.dur_worker = worker = DurationWorker(videos, self)
        worker.done.connect(lambda durations, starts: self._durations_ready(worker, durations, starts))
        worker.finished.connect(worker.deleteLater)
        worker.start()
        self.statusBar().showMessage(CALCULATING)
        self._update_playback()

    def _durations_ready(self, worker, durations, starts):
        if worker is not self.dur_worker:  # llegó tarde: ya se abrió otra ruta
            return
        timeline = Timeline(worker.paths, durations)
        self.starts = {path.name: start for path, start in zip(worker.paths, starts)}
        if self.statusBar().currentMessage() == CALCULATING:
            self.statusBar().clearMessage()
        if timeline.total <= 0:
            self.statusBar().showMessage("No se pudo calcular la duración")
            return
        self.timeline = timeline
        self.bar.set_timeline(timeline, starts)
        self._update_playback()

    def _show(self, seconds, mode):
        """Pone en la vista el cuadro limpio del instante global `seconds`; devuelve el instante global real, None si no cambió.

        mode: "precise" (seek: cae en el primer cuadro >= t, tarda), "drag" (salto directo, aproximado) o "play" (secuencial).
        """
        # ponytail: decodifica en el hilo de la UI; a 16x (~240 cuadros/s) puede ir a tirones. Mover a un hilo si se traba.
        path, local = self.timeline.locate(seconds)
        if path != self.cap_path:
            if self.cap:
                self.cap.release()
            self.cap, self.cap_path, self.cap_t = cv2.VideoCapture(str(path)), path, -1e9
            fps = self.cap.get(cv2.CAP_PROP_FPS)
            self.cap_fps = fps if fps > 0 else 15
        delta = local - self.cap_t
        if mode == "play" and -SEQUENTIAL_MAX < delta < 0:
            return None  # el cuadro mostrado ya es posterior (el cuadro leído cae un poco después)
        if mode == "play" and 0 <= delta <= SEQUENTIAL_MAX:
            skip = int(delta * self.cap_fps)
            if skip < 1:
                return None  # todavía no toca el siguiente cuadro
            for _ in range(skip - 1):
                self.cap.grab()
            ok, frame = self.cap.read()
            real = self.cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
        elif mode == "drag":
            self.cap.set(cv2.CAP_PROP_POS_MSEC, local * 1000)
            ok, frame = self.cap.read()
            real = self.cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
        else:
            real = seek(self.cap, local)
            ok, frame = (False, None) if real is None else self.cap.retrieve()
        if not ok:
            self.cap_t = -1e9
            return None
        self.cap_t = real
        self.view.set_frame(to_qimage(frame))
        now = time.monotonic()
        if mode != "play" or now - self._clock_at >= CLOCK_INTERVAL:
            self.wall, self._clock_at = read_clock(frame), now
        return self.timeline.to_global(path, real)

    def _scrub(self, seconds, mode="precise"):
        if not self.timeline:
            return
        self.position = min(max(seconds, 0.0), self.timeline.total)
        if mode == "drag" and time.monotonic() - self._shown < SCRUB_INTERVAL:
            return self.bar.set_position(self.position, self.wall)
        self._shown = time.monotonic()
        if mode == "precise":
            self.statusBar().showMessage(SEEKING)
            self.statusBar().repaint()  # sin procesar eventos, para que no parezca colgado
        real = self._show(self.position, mode)
        if mode == "precise" and self.statusBar().currentMessage() == SEEKING:
            self.statusBar().clearMessage()
        # la posición mostrada es la real: tras un hueco, el siguiente cuadro existente
        if real is not None and (mode == "precise" or (mode == "play" and abs(real - self.position) > 1)):
            self.position = real
        self.bar.set_position(self.position, self.wall)

    def _on_seek(self, seconds, final):
        self.scrubbing = not final
        self._scrub(seconds, "precise" if final else "drag")

    def _goto_mark(self, seconds):
        self._stop_play()
        self._scrub(seconds - LEAD)

    def toggle_play(self):
        if self.playing:
            return self._stop_play()
        if self.position >= self.timeline.total:
            self._scrub(0.0)
        self.playing = True
        self._last_tick = time.monotonic()
        self.play_button.setText("Pausa")
        self.tick.start()

    def _stop_play(self):
        self.playing = False
        self.tick.stop()
        self.play_button.setText("Reproducir")

    def _tick(self):
        now = time.monotonic()
        dt, self._last_tick = now - self._last_tick, now
        if self.scrubbing:
            return
        self._scrub(self.position + dt * self.speed, "play")
        if self.position >= self.timeline.total:
            self._stop_play()

    def show_first_frame(self, item):
        if not self.folder_button.isEnabled():  # procesando
            return
        if self.timeline:
            return self._scrub(self.timeline.offsets[self.video_list.row(item)])  # la barra salta al inicio de ese video
        path = item.data(Qt.ItemDataRole.UserRole)
        frame = first_frame(path)
        if frame is None:
            self.statusBar().showMessage(f"No se pudo abrir: {path.name}")
        else:
            self.view.set_frame(to_qimage(frame))  # el área dibujada se conserva

    def start(self):
        self._reset()
        self.statusBar().showMessage("Cargando modelo…")
        items = self._items()
        row = max(self.video_list.currentRow(), 0)
        items[row].setCheckState(Qt.CheckState.Checked)  # empieza desde el seleccionado
        self.run_items = [item for item in items[row:] if item.checkState() == Qt.CheckState.Checked]
        paths = [item.data(Qt.ItemDataRole.UserRole) for item in self.run_items]
        self.running, self.finished = set(), 0
        self.show_progress()
        self._busy(True)
        self.cap_t = -1e9  # la vista va a mostrar otra cosa: la próxima lectura salta
        self.worker = worker = Worker(paths, self.view.polygon)
        worker.frame.connect(self.view.set_frame)
        worker.mark.connect(self.bar.add_mark)
        worker.counts.connect(self.show_counts)
        worker.file_started.connect(self.file_started)
        worker.file_finished.connect(self.file_finished)
        worker.file_skipped.connect(lambda name: self.file_label.setText(f"No se pudo abrir: {name}"))
        worker.provider.connect(self.set_provider)
        worker.fps.connect(self.show_fps)
        worker.done.connect(self.show_table)
        worker.error.connect(self.show_error)
        worker.start()

    def show_fps(self, fps):
        if not self.paused:
            self.statusBar().showMessage(f"{self.provider} · {fps:.0f} fps")

    def file_started(self, index):
        self.running.add(index)
        self.show_progress()

    def file_finished(self, index):
        self.running.discard(index)
        self.finished += 1
        self.show_progress()

    def show_progress(self):
        self.file_label.setText(f"Videos: {self.finished}/{len(self.run_items)}")
        for item in self._items():
            item.setBackground(QBrush())
        for index in self.running:
            self.run_items[index].setBackground(QColor(255, 220, 120))
        if self.running:
            self.video_list.scrollToItem(self.run_items[min(self.running)])

    def toggle_pause(self):
        self.paused = not self.paused
        self.pause_button.setText("Reanudar" if self.paused else "Pausar")
        if self.paused:
            self.worker.pause()
            self.statusBar().showMessage("En pausa")
        else:
            self.worker.resume()
            self.statusBar().showMessage(self.provider)

    def stop(self):
        self.stop_button.setEnabled(False)
        self.pause_button.setEnabled(False)
        self.worker.stop()

    def set_provider(self, provider):
        self.provider = provider
        self.statusBar().showMessage(provider)

    def show_counts(self, count):
        self.count_label.setText(f"Subidas: {count}")

    def _finish(self):
        self.worker.wait()
        self._busy(False)
        item = self.video_list.currentItem()
        if item:
            self.show_first_frame(item)  # imagen limpia para volver a dibujar el área

    def show_table(self, rows):
        self.table.setRowCount(len(rows) + 1)
        total = 0
        for row, (name, count) in enumerate(rows):
            self.table.setItem(row, 0, QTableWidgetItem(name))
            self.table.setItem(row, 1, QTableWidgetItem("no se pudo abrir" if count is None else str(count)))
            self.table.setItem(row, 2, QTableWidgetItem(clock_text(self.starts[name]) if self.starts.get(name) else ""))
            total += count or 0
        self.table.setItem(len(rows), 0, QTableWidgetItem("TOTAL"))
        self.table.setItem(len(rows), 1, QTableWidgetItem(str(total)))
        self._finish()

    def show_error(self, message):
        QMessageBox.critical(self, TITLE, message)
        self._finish()

    def closeEvent(self, event):
        self._stop_play()
        if self.cap:
            self.cap.release()
        for thread in self.findChildren(DurationWorker):
            thread.requestInterruption()
            thread.wait()
        if self.worker:
            self.worker.stop()
            self.worker.wait()
        super().closeEvent(event)
