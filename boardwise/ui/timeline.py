from PySide6.QtCore import QRectF, Qt, QThread, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QToolTip, QWidget

from boardwise.core.timeline import durations as cached_durations

PAD = 8
NEAR_PX = 5  # distancia al clic para tomarlo como clic en una marca


def hms(seconds):
    seconds = int(seconds)
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


class DurationWorker(QThread):
    done = Signal(list)

    def __init__(self, paths, parent):
        super().__init__(parent)
        self.paths = list(paths)

    def run(self):
        durations = cached_durations(self.paths, self.isInterruptionRequested)
        if durations is not None:
            self.done.emit(durations)


class TimelineBar(QWidget):
    """Barra de toda la carpeta: posición, separadores entre archivos y una marca por subida."""

    seek = Signal(float, bool)  # tiempo global; True = soltó el ratón
    mark_clicked = Signal(float)

    def __init__(self):
        super().__init__()
        self.setFixedHeight(48)
        self.setMouseTracking(True)
        self.timeline = None
        self.position = 0.0
        self.marks = []  # (video, segundo en el video)
        self._drag = False

    def set_timeline(self, timeline):
        self.timeline = timeline
        self.update()

    def set_position(self, seconds):
        self.position = seconds
        self.update()

    def clear_marks(self):
        self.marks = []
        self.update()

    def add_mark(self, path, seconds):
        self.marks.append((path, seconds))
        self.update()

    def sorted_marks(self):
        """[(tiempo global, número de subida, video)] en orden de tiempo."""
        if not self.timeline:
            return []
        rows = sorted((self.timeline.to_global(path, seconds), path) for path, seconds in self.marks)
        return [(t, n, path) for n, (t, path) in enumerate(rows, 1)]

    def x_of(self, seconds):
        return PAD + seconds / self.timeline.total * (self.width() - 2 * PAD)

    def _time_at(self, x):
        return min(max((x - PAD) / (self.width() - 2 * PAD), 0.0), 1.0) * self.timeline.total

    def _mark_near(self, x):
        near = [mark for mark in self.sorted_marks() if abs(self.x_of(mark[0]) - x) <= NEAR_PX]
        return min(near, key=lambda mark: abs(self.x_of(mark[0]) - x), default=None)

    def paintEvent(self, event):
        painter = QPainter(self)
        palette = self.palette()
        painter.fillRect(self.rect(), palette.window())
        if not self.timeline:
            return
        timeline = self.timeline
        painter.setPen(palette.text().color())
        name = timeline.locate(self.position)[0].name
        painter.drawText(PAD, 14, f"{hms(self.position)} / {hms(timeline.total)}   ·   {name}")
        painter.fillRect(QRectF(PAD, 28, self.width() - 2 * PAD, 6), palette.mid())
        painter.fillRect(QRectF(PAD, 28, self.x_of(self.position) - PAD, 6), palette.highlight())
        separator = QColor(palette.text().color())
        separator.setAlpha(70)
        painter.setPen(separator)
        for offset in timeline.offsets[1:]:
            x = self.x_of(offset)
            painter.drawLine(int(x), 24, int(x), 38)
        painter.setPen(QPen(QColor(220, 40, 40), 2))
        for t, _, _ in self.sorted_marks():
            x = int(self.x_of(t))
            painter.drawLine(x, 22, x, 40)
        painter.setPen(QPen(palette.text().color(), 1))
        painter.setBrush(palette.base())
        painter.drawEllipse(QRectF(self.x_of(self.position) - 5, 26, 10, 10))

    def mousePressEvent(self, event):
        if not self.timeline or event.button() != Qt.MouseButton.LeftButton:
            return
        mark = self._mark_near(event.position().x())
        if mark:
            return self.mark_clicked.emit(mark[0])
        self._drag = True
        self.seek.emit(self._time_at(event.position().x()), False)

    def mouseMoveEvent(self, event):
        if not self.timeline:
            return
        x = event.position().x()
        if self._drag:
            return self.seek.emit(self._time_at(x), False)
        mark = self._mark_near(x)
        if mark:
            QToolTip.showText(event.globalPosition().toPoint(), f"Subida {mark[1]} · {hms(mark[0])} · {mark[2].name}", self)
        else:
            QToolTip.hideText()

    def mouseReleaseEvent(self, event):
        if self._drag:
            self._drag = False
            self.seek.emit(self._time_at(event.position().x()), True)
