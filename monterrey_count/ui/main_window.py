from pathlib import Path

import cv2
from PySide6.QtCore import QPointF, QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from monterrey_count import updater
from monterrey_count.core.pipeline import VIDEO_EXTENSIONS, list_videos
from monterrey_count.ui.worker import Worker, to_qimage

TITLE = "Monterrey Count"
BIG = "font-size: 28px; font-weight: bold"


class VideoView(QWidget):
    """Muestra el cuadro escalado con su aspecto y deja trazar la línea en coordenadas del video."""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(640, 360)
        self.pix = None
        self.line = None  # ((x1, y1), (x2, y2)) en píxeles del video; None = no dibujar
        self._anchor = None

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

    def mousePressEvent(self, event):
        if self.pix:
            self._anchor = self._to_video(event.position())

    def mouseMoveEvent(self, event):
        if self._anchor:
            end = self._to_video(event.position())
            if end != self._anchor:
                self.line = (self._anchor, end)
                self.update()

    def mouseReleaseEvent(self, event):
        self._anchor = None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        if not self.pix:
            return
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(self._rect(), self.pix)
        if self.line:
            painter.setPen(QPen(QColor(0, 255, 0), 3))
            painter.drawLine(self._to_view(self.line[0]), self._to_view(self.line[1]))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{TITLE} v{updater.current_version()}")
        self.source = None
        self.worker = None
        self.provider = ""

        self.folder_button = QPushButton("Abrir carpeta…")
        self.video_button = QPushButton("Abrir video…")
        self.path_label = QLabel("Elige una carpeta o un video")
        self.view = VideoView()
        self.start_button = QPushButton("Iniciar")
        self.stop_button = QPushButton("Detener")
        self.in_label = QLabel()
        self.out_label = QLabel()
        self.file_label = QLabel()
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Archivo", "Entradas", "Salidas"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMaximumHeight(180)
        for label in (self.in_label, self.out_label):
            label.setStyleSheet(BIG)

        top = QHBoxLayout()
        for widget in (self.folder_button, self.video_button, self.path_label):
            top.addWidget(widget)
        top.setStretch(2, 1)
        controls = QHBoxLayout()
        for widget in (self.start_button, self.stop_button, self.in_label, self.out_label, self.file_label):
            controls.addWidget(widget)
        controls.setStretch(4, 1)
        layout = QVBoxLayout()
        layout.addLayout(top)
        layout.addWidget(QLabel("Arrastra sobre el video para trazar la línea de conteo"))
        layout.addWidget(self.view, 1)
        layout.addLayout(controls)
        layout.addWidget(self.table)
        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

        self.folder_button.clicked.connect(self.open_folder)
        self.video_button.clicked.connect(self.open_video)
        self.start_button.clicked.connect(self.start)
        self.stop_button.clicked.connect(self.stop)
        self._reset()
        self._busy(False)
        self.start_button.setEnabled(False)
        self.resize(1000, 800)

    def _reset(self):
        self.in_label.setText("Entradas: 0")
        self.out_label.setText("Salidas: 0")
        self.file_label.clear()
        self.table.clearSpans()
        self.table.setRowCount(0)

    def _busy(self, busy):
        for widget in (self.folder_button, self.video_button, self.view, self.start_button):
            widget.setEnabled(not busy)
        self.stop_button.setEnabled(busy)

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
            capture = cv2.VideoCapture(str(video))
            ok, frame = capture.read()
            capture.release()
            if ok:
                break
        else:
            QMessageBox.warning(self, TITLE, "No se pudo abrir ningún video de esa ruta.")
            return
        self.source = path
        self.path_label.setText(f"{path}  ({len(videos)} videos)" if path.is_dir() else str(path))
        self._reset()
        self.view.set_frame(to_qimage(frame))
        height, width = frame.shape[:2]
        self.view.line = ((0, height // 2), (width, height // 2))
        self.start_button.setEnabled(True)

    def start(self):
        self._reset()
        self._busy(True)
        self.statusBar().showMessage("Cargando modelo…")
        self.worker = worker = Worker(self.source, *self.view.line)
        worker.frame.connect(self.view.set_frame)
        worker.counts.connect(self.show_counts)
        worker.file_changed.connect(lambda i, n, name: self.file_label.setText(f"Archivo {i}/{n}: {name}"))
        worker.file_skipped.connect(lambda name: self.file_label.setText(f"No se pudo abrir: {name}"))
        worker.provider.connect(self.set_provider)
        worker.fps.connect(lambda fps: self.statusBar().showMessage(f"{self.provider} · {fps:.0f} fps"))
        worker.done.connect(self.show_table)
        worker.error.connect(self.show_error)
        worker.start()

    def stop(self):
        self.stop_button.setEnabled(False)
        self.worker.requestInterruption()

    def set_provider(self, provider):
        self.provider = provider
        self.statusBar().showMessage(provider)

    def show_counts(self, in_count, out_count):
        self.in_label.setText(f"Entradas: {in_count}")
        self.out_label.setText(f"Salidas: {out_count}")

    def _finish(self):
        self.worker.wait()
        self._busy(False)

    def show_table(self, rows):
        self.table.setRowCount(len(rows) + 1)
        total_in = total_out = 0
        for row, (name, entered, left) in enumerate(rows):
            self.table.setItem(row, 0, QTableWidgetItem(name))
            if entered is None:
                self.table.setItem(row, 1, QTableWidgetItem("no se pudo abrir"))
                self.table.setSpan(row, 1, 1, 2)
            else:
                self.table.setItem(row, 1, QTableWidgetItem(str(entered)))
                self.table.setItem(row, 2, QTableWidgetItem(str(left)))
                total_in += entered
                total_out += left
        for column, text in enumerate(("TOTAL", str(total_in), str(total_out))):
            self.table.setItem(len(rows), column, QTableWidgetItem(text))
        self._finish()

    def show_error(self, message):
        QMessageBox.critical(self, TITLE, message)
        self._finish()

    def closeEvent(self, event):
        if self.worker:
            self.worker.requestInterruption()
            self.worker.wait()
        super().closeEvent(event)
