from pathlib import Path

import cv2
from PySide6.QtCore import QPointF, QRect, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow,
                               QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from monterrey_count import updater
from monterrey_count.core.pipeline import VIDEO_EXTENSIONS, list_videos
from monterrey_count.ui.worker import Worker, to_qimage

TITLE = "Monterrey Count"
BIG = "font-size: 28px; font-weight: bold"
PANEL_WIDTH = 260
CLOSE_PX = 10  # distancia en pantalla al primer vértice para cerrar el área


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

        self.folder_button = QPushButton("Abrir carpeta…")
        self.video_button = QPushButton("Abrir video…")
        self.path_label = QLabel("Elige una carpeta o un video")
        self.view = VideoView()
        self.start_button = QPushButton("Iniciar")
        self.pause_button = QPushButton("Pausar")
        self.stop_button = QPushButton("Detener")
        self.clear_button = QPushButton("Borrar área")
        self.count_label = QLabel()
        self.file_label = QLabel()
        self.video_list = QListWidget()
        self.all_button = QPushButton("Todos")
        self.none_button = QPushButton("Ninguno")
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Archivo", "Subidas"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMaximumHeight(180)
        self.count_label.setStyleSheet(BIG)

        top = QHBoxLayout()
        for widget in (self.folder_button, self.video_button, self.clear_button, self.path_label):
            top.addWidget(widget)
        top.setStretch(3, 1)
        controls = QHBoxLayout()
        for widget in (self.start_button, self.pause_button, self.stop_button, self.count_label, self.file_label):
            controls.addWidget(widget)
        controls.setStretch(4, 1)
        layout = QVBoxLayout()
        layout.addLayout(top)
        layout.addWidget(QLabel("Haz clic en las esquinas del área; doble clic para cerrar"))
        layout.addWidget(self.view, 1)
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

    def _busy(self, busy):
        for widget in (self.folder_button, self.video_button, self.view, self.clear_button):
            widget.setEnabled(not busy)
        self.stop_button.setEnabled(busy)
        self.pause_button.setEnabled(busy)
        self.pause_button.setText("Pausar")
        self.paused = False
        for widget in (self.all_button, self.none_button):
            widget.setEnabled(not busy)
        for item in self._items():  # con la lista bloqueada no se pueden marcar
            flags = item.flags() | Qt.ItemFlag.ItemIsUserCheckable
            item.setFlags(flags & ~Qt.ItemFlag.ItemIsUserCheckable if busy else flags)
            item.setBackground(QBrush())
        self._update_start()

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
        self.video_list.clear()
        for item_path in videos:
            item = QListWidgetItem(item_path.name)
            item.setData(Qt.ItemDataRole.UserRole, item_path)
            item.setCheckState(Qt.CheckState.Checked)
            self.video_list.addItem(item)
        self.video_list.setCurrentRow(videos.index(video))
        self.view.set_frame(to_qimage(frame))
        self.view.set_default_area()

    def show_first_frame(self, item):
        if not self.folder_button.isEnabled():  # procesando
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        frame = first_frame(path)
        if frame is None:
            self.statusBar().showMessage(f"No se pudo abrir: {path.name}")
        else:
            self.view.set_frame(to_qimage(frame))  # el área dibujada se conserva

    def start(self):
        self._reset()
        self._busy(True)
        self.statusBar().showMessage("Cargando modelo…")
        paths = [item.data(Qt.ItemDataRole.UserRole) for item in self._checked()]
        self.worker = worker = Worker(paths, self.view.polygon)
        worker.frame.connect(self.view.set_frame)
        worker.counts.connect(self.show_counts)
        worker.file_changed.connect(self.show_file)
        worker.file_skipped.connect(lambda name: self.file_label.setText(f"No se pudo abrir: {name}"))
        worker.provider.connect(self.set_provider)
        worker.fps.connect(self.show_fps)
        worker.done.connect(self.show_table)
        worker.error.connect(self.show_error)
        worker.start()

    def show_fps(self, fps):
        if not self.paused:
            self.statusBar().showMessage(f"{self.provider} · {fps:.0f} fps")

    def show_file(self, index, total, name):
        self.file_label.setText(f"Videos: {index}/{total} · {name}")
        current = self._checked()[index - 1]
        for item in self._items():
            item.setBackground(QColor(255, 220, 120) if item is current else QBrush())
        self.video_list.scrollToItem(current)

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

    def show_table(self, rows):
        self.table.setRowCount(len(rows) + 1)
        total = 0
        for row, (name, count) in enumerate(rows):
            self.table.setItem(row, 0, QTableWidgetItem(name))
            self.table.setItem(row, 1, QTableWidgetItem("no se pudo abrir" if count is None else str(count)))
            total += count or 0
        self.table.setItem(len(rows), 0, QTableWidgetItem("TOTAL"))
        self.table.setItem(len(rows), 1, QTableWidgetItem(str(total)))
        self._finish()

    def show_error(self, message):
        QMessageBox.critical(self, TITLE, message)
        self._finish()

    def closeEvent(self, event):
        if self.worker:
            self.worker.stop()
            self.worker.wait()
        super().closeEvent(event)
